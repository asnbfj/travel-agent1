"""Agent API 路由"""
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.agent.graph import run_travel_agent
from app.agent.memory import (
    save_message,
    get_conversation_history,
    clear_conversation_history,
)
from app.schemas.agent import (
    AgentMessageRequest,
    AgentMessageResponse,
    AgentPdfExportRequest,
    ChatHistoryResponse,
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
    """
    try:
        # 保存用户消息
        await save_message(
            user_id=str(current_user.id),
            role="user",
            content=request.message,
            db=db,
        )

        # 运行 Agent
        result = await run_travel_agent(
            user_id=str(current_user.id),
            user_message=request.message,
            context=request.context,
        )

        # 保存 AI 回复
        await save_message(
            user_id=str(current_user.id),
            role="assistant",
            content=result.get("response", ""),
            db=db,
            metadata={
                "intent": result.get("intent"),
                "tool_calls": result.get("tool_calls"),
            },
        )

        return AgentMessageResponse(
            message=result.get("response", ""),
            intent=result.get("intent"),
            suggested_actions=result.get("suggested_actions", []),
            itinerary=result.get("itinerary"),
            weather_info=result.get("weather_info"),
            tool_calls=result.get("tool_calls", []),
        )
    except Exception as e:
        logger.error(f"Agent 处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"Agent 处理失败: {str(e)}")


@router.post("/export/pdf", tags=["Agent"])
async def export_itinerary_pdf(
    request: AgentPdfExportRequest,
    current_user: User = Depends(get_current_user),
):
    """把行程导出为 PDF 并下载

    文字为真实文本（可选中、可搜索），中文字体使用 ReportLab 内置 CID 字体，
    不依赖任何字体文件或在目标机器上安装字体。
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


@router.get("/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取对话历史"""
    messages = await get_conversation_history(
        user_id=str(current_user.id),
        db=db,
        limit=limit,
        offset=offset,
    )
    return ChatHistoryResponse(
        messages=messages,
        total=len(messages),
        has_more=len(messages) == limit,
    )


@router.delete("/history")
async def clear_chat_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清除对话历史"""
    count = await clear_conversation_history(
        user_id=str(current_user.id),
        db=db,
    )
    return {"message": f"已清除 {count} 条对话记录"}
