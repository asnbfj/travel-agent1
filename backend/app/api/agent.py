"""Agent API 路由"""
import json
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, AsyncSessionLocal
from app.agent.graph import run_travel_agent, run_travel_agent_stream
from app.agent.memory import (
    ConversationNotFound,
    append_message,
    count_conversations,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations,
)
from app.schemas.agent import (
    AgentMessageRequest,
    AgentMessageResponse,
    AgentPdfExportRequest,
    ConversationDetailResponse,
    ConversationListResponse,
)
from app.services.pdf_service import build_itinerary_pdf
from app.utils.auth import get_current_user
from app.models.user import User
import logging
from datetime import datetime

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])
logger = logging.getLogger(__name__)

# 从 Markdown 里提取标题用的候选标题行
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
# 文件名里需要剔除的字符（路径分隔符与控制字符等）
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


@router.post("/chat", response_model=AgentMessageResponse)
async def chat_with_agent(
    request: AgentMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    与旅行规划 Agent 对话
    用户输入旅行需求，Agent 返回完整的行程规划

    不传 `conversation_id` 时自动开一段新会话，并在响应里回传新会话 ID。
    """
    user_id = str(current_user.id)

    # 1) 解析会话：显式指定则校验归属，否则新建
    if request.conversation_id:
        conversation = await get_conversation(db, user_id, request.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        conversation = await create_conversation(db, user_id)

    try:
        # 2) 先落用户消息：Agent 失败也不会丢掉这次提问
        user_message = await append_message(db, conversation.id, "user", request.message)

        # 3) 运行 Agent（历史只取本会话，且排除刚入库的本轮提问）
        result = await run_travel_agent(
            user_id=user_id,
            user_message=request.message,
            context=request.context,
            conversation_id=str(conversation.id),
            exclude_message_id=str(user_message.id),
        )

        # 4) 保存 AI 回复与本轮结构化结果
        await append_message(
            db,
            conversation.id,
            "assistant",
            result.get("response", ""),
            meta={
                "intent": result.get("intent"),
                "tool_calls": result.get("tool_calls"),
                "weather_info": result.get("weather_info"),
                "suggested_actions": result.get("suggested_actions"),
            },
        )

        return AgentMessageResponse(
            message=result.get("response", ""),
            intent=result.get("intent"),
            suggested_actions=result.get("suggested_actions", []),
            itinerary=result.get("itinerary"),
            weather_info=result.get("weather_info"),
            tool_calls=result.get("tool_calls", []),
            conversation_id=str(conversation.id),
        )
    except Exception as e:
        logger.error(f"Agent 处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"Agent 处理失败: {str(e)}")


def _sse(payload: dict) -> str:
    """把事件编码成 SSE 的一帧

    `json.dumps` 会把换行转义掉，所以正文里带 Markdown 换行也不会破坏协议。
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/stream", tags=["Agent"])
async def chat_with_agent_stream(
    request: AgentMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """与 Agent 对话，并以 SSE 实时推送执行过程

    每帧形如 `data: {"type": "...", ...}`，`type` 取值：
    `stage`（阶段）/ `tool_start` / `tool_end` / `retry` / `error`，
    最后一帧固定是 `done`，带 `message` / `weather_info` / `tool_calls` /
    `suggested_actions` / `conversation_id`，结构与非流式 `/chat` 一致。

    前端据此显示「执行到哪一步」；即使中途失败也会以 `error` + `done` 收尾，
    不会让界面一直停在加载态。
    """
    user_id = str(current_user.id)

    # 1) 会话与用户消息在这里落库：此时请求级 db 仍然可用
    if request.conversation_id:
        conversation = await get_conversation(db, user_id, request.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        conversation = await create_conversation(db, user_id)

    conversation_id = str(conversation.id)
    user_message = await append_message(db, conversation_id, "user", request.message)

    async def event_stream():
        result: dict = {}
        try:
            async for event in run_travel_agent_stream(
                user_id=user_id,
                user_message=request.message,
                context=request.context,
                conversation_id=conversation_id,
                exclude_message_id=str(user_message.id),
            ):
                if event.get("type") != "done":
                    yield _sse(event)
                    continue

                result = event.get("result") or {}
                text = result.get("response", "")

                # 2) 保存 AI 回复。这里必须另开会话：请求级 db 会在响应体
                #    开始发送前被依赖注入收尾关闭，流式生成器不能依赖它。
                try:
                    async with AsyncSessionLocal() as save_db:
                        await append_message(
                            save_db,
                            conversation_id,
                            "assistant",
                            text,
                            meta={
                                "intent": result.get("intent"),
                                "tool_calls": result.get("tool_calls") or [],
                                "weather_info": result.get("weather_info"),
                                "suggested_actions": result.get("suggested_actions") or [],
                            },
                        )
                except Exception:  # noqa: BLE001 - 落库失败不应该吞掉已经生成的回复
                    logger.exception("⚠ 保存 AI 回复失败（会话 %s）", conversation_id)

                yield _sse(
                    {
                        "type": "done",
                        "conversation_id": conversation_id,
                        "message": text,
                        "intent": result.get("intent"),
                        "weather_info": result.get("weather_info"),
                        "tool_calls": result.get("tool_calls") or [],
                        "suggested_actions": result.get("suggested_actions") or [],
                    }
                )
        except ConversationNotFound:
            yield _sse({"type": "error", "text": "会话不存在"})
        except Exception as e:  # noqa: BLE001 - 出错也要给前端一个收尾帧
            logger.exception("❌ 流式对话失败")
            yield _sse({"type": "error", "text": f"处理失败：{type(e).__name__}: {e}"})
            yield _sse(
                {
                    "type": "done",
                    "conversation_id": conversation_id,
                    "message": "",
                    "weather_info": None,
                    "tool_calls": [],
                    "suggested_actions": [],
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 关闭 Nginx 等反向代理的缓冲，否则事件会被攒着一起发
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/export/pdf", tags=["Agent"])
async def export_itinerary_pdf(
    request: AgentPdfExportRequest,
    current_user: User = Depends(get_current_user),
):
    """把行程导出为 PDF 并下载

    文字为真实文本（可选中、可搜索）。中文字体来自随仓库分发的
    `assets/fonts/NotoSansSC-{Regular,Bold}.ttf`（SIL OFL 1.1），
    因此加粗是真正的 Bold 字重；不需要在目标机器上安装任何系统字体。
    """
    content = (request.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="行程内容为空，无法生成 PDF")

    # 标题：优先用调用方传入的，否则从正文首个标题行提取
    title = (request.title or "").strip()
    if not title:
        match = _HEADING_RE.search(content)
        title = match.group(1).strip() if match else "旅行行程规划"
    title = _UNSAFE_FILENAME_RE.sub(" ", title).strip() or "旅行行程规划"

    try:
        pdf_bytes = build_itinerary_pdf(
            title=title,
            content=content,
            weather_info=request.weather_info,
            destination=request.destination,
        )
    except ValueError as e:  # 正文为空等可预期的入参问题
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 - 渲染失败要给出明确原因，不返回损坏的文件
        logger.exception("❌ 生成行程 PDF 失败")
        raise HTTPException(status_code=500, detail=f"生成 PDF 失败：{type(e).__name__}: {e}")

    filename = f"TravelAI-{title}-{datetime.now().strftime('%Y%m%d')}.pdf"
    logger.info("📄 导出行程 PDF: %s (%d bytes)", filename, len(pdf_bytes))

    # 中文文件名用 RFC 5987 的 filename* 传递，同时给出 ASCII 回退名
    disposition = (
        'attachment; filename="travelai-itinerary.pdf"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(pdf_bytes)),
            # 每次内容不同，禁止中间层缓存
            "Cache-Control": "no-store",
        },
    )


@router.get("/tools/status", tags=["Agent"])
async def get_tools_status():
    """查看线上工具与 LLM 的配置状态

    严格线上模式下，缺 Key 会导致对应功能直接报错。
    此接口用于快速定位「哪个 Key 还没配」，无需翻日志。
    """
    from app.agent.graph import check_tool_config
    from app.llm.client import check_llm_config, LLMConfigError
    from app.agent.tools import ALL_TOOLS
    from app.config import get_settings

    settings = get_settings()

    llm_ok = True
    llm_error = None
    try:
        check_llm_config()
    except LLMConfigError as e:
        llm_ok = False
        llm_error = str(e)

    missing = check_tool_config()

    return {
        "strict_online": settings.STRICT_ONLINE,
        "llm": {
            "provider": settings.LLM_PROVIDER,
            "ready": llm_ok,
            "error": llm_error,
        },
        "tools": [
            {
                "name": tool.name,
                "description": (tool.description or "").split("\n")[0],
            }
            for tool in ALL_TOOLS
        ],
        "missing_config": missing,
        "ready": llm_ok and not missing,
    }


@router.get("/conversations", response_model=ConversationListResponse)
async def list_user_conversations(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的会话列表（按最近使用倒序）

    左侧会话栏据此渲染；`preview` 与 `message_count` 让列表项无需再逐个拉详情。
    """
    user_id = str(current_user.id)
    conversations = await list_conversations(db, user_id, limit=limit, offset=offset)
    total = await count_conversations(db, user_id)
    return ConversationListResponse(conversations=conversations, total=total)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation_detail(
    conversation_id: str,
    limit: int = 200,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取某个会话及其全部消息"""
    conversation = await get_conversation(db, str(current_user.id), conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = await get_messages(db, str(conversation.id), limit=limit, offset=offset)
    return ConversationDetailResponse(
        id=str(conversation.id),
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages,
    )


@router.delete("/conversations/{conversation_id}")
async def delete_user_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除会话（连同其中的消息）"""
    deleted = await delete_conversation(db, str(current_user.id), conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"message": "会话已删除"}
