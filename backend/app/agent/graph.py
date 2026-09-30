"""LangGraph Agent 构建（tool-calling / ReAct 循环）

架构：模型绑定 4 个真实工具，由模型自主决定调用哪些工具、调用几轮。
      call_model -> (有 tool_calls?) -> tools -> call_model -> ... -> END

已移除原固定流水线与 RAG 检索。
"""
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple
from datetime import datetime
import asyncio
import logging
import time

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import tools_condition

from app.agent.state import AgentState
from app.agent.nodes import build_system_prompt, call_model, build_tool_node
from app.agent.tools import ALL_TOOLS, start_collector
from app.agent.progress import describe_args, start_progress, stage, tool_display
from app.llm.client import check_llm_config, LLMConfigError
from app.config import get_settings

logger = logging.getLogger(__name__)

# 最多允许多少轮「模型 <-> 工具」往返（防死循环）
MAX_TOOL_ROUNDS = 8
# 默认的建议操作
DEFAULT_ACTIONS = [
    "调整行程天数",
    "换成其他目的地",
    "查询当地天气",
    "查询酒店住宿",
    "规划景点间路线",
]
# 行程类回复才提供「导出 PDF」入口：短问答（例如只查了天气）导出 PDF 没有意义
EXPORT_PDF_ACTION = "导出 PDF 行程"
# 判定「像一份行程」的正文长度下限
ITINERARY_MIN_LENGTH = 400


def build_suggested_actions(response_text: str) -> List[str]:
    """按回复内容给出建议操作

    只有看起来是完整行程的回复才追加「导出 PDF 行程」，
    避免在「明天天气怎么样」这类短回答下给出无意义的导出入口。
    """
    actions = list(DEFAULT_ACTIONS)
    text = response_text or ""
    if len(text) >= ITINERARY_MIN_LENGTH and ("Day" in text or "行程" in text):
        actions.insert(0, EXPORT_PDF_ACTION)
    return actions


def create_travel_agent_graph():
    """创建旅行规划 Agent 图"""
    graph = StateGraph(AgentState)

    graph.add_node("agent", call_model)
    graph.add_node("tools", build_tool_node())

    graph.set_entry_point("agent")

    # 模型要求调用工具 -> 执行工具；否则结束
    # 注意：tools_condition 的返回值为 'action' / '__end__'
    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {"action": "tools", "__end__": END},
    )
    graph.add_edge("tools", "agent")

    compiled = graph.compile()
    logger.info("✅ TravelAI Agent 图构建完成（tool-calling 模式，工具数=%d）", len(ALL_TOOLS))
    return compiled


# 全局 Agent 实例
_travel_agent = None


def get_travel_agent():
    """获取 Agent 实例（单例）"""
    global _travel_agent
    if _travel_agent is None:
        _travel_agent = create_travel_agent_graph()
    return _travel_agent


def check_tool_config() -> List[str]:
    """检查线上工具所需的 Key，返回缺失项说明（供启动日志与诊断接口使用）"""
    settings = get_settings()
    missing: List[str] = []
    if not settings.AMAP_API_KEY:
        missing.append("AMAP_API_KEY（高德地图：天气查询、路线规划）")
    if not settings.BOCHA_API_KEY:
        missing.append("BOCHA_API_KEY（博查 AI 搜索：景点、必玩地点、酒店）")
    return missing


async def _load_history(
    conversation_id: Optional[str],
    limit: int = 10,
    exclude_message_id: Optional[str] = None,
) -> List[BaseMessage]:
    """加载当前会话的最近历史，转换为 LangChain 消息

    只取**本会话**的记录，避免把几次无关的咨询混进同一段上下文。
    """
    try:
        from app.agent.memory import load_history_for_agent

        records = await load_history_for_agent(
            conversation_id=conversation_id,
            limit=limit,
            exclude_message_id=exclude_message_id,
        )
    except Exception as e:  # 历史加载失败不应阻断主流程
        logger.warning(f"⚠ 加载对话历史失败，忽略：{e}")
        return []

    messages: List[BaseMessage] = []
    for record in records or []:
        content = (record.get("content") or "").strip()
        if not content:
            continue
        role = record.get("role")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def _final_text(messages: List[BaseMessage]) -> str:
    """取最后一条 AI 回复的文本"""
    for message in reversed(messages or []):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, list):  # 多模态分片
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            text = (content or "").strip()
            if text:
                return text
    return ""


async def _prepare_messages(
    user_message: str,
    context: Optional[dict],
    conversation_id: Optional[str],
    exclude_message_id: Optional[str],
) -> List[BaseMessage]:
    """组装「系统提示 + 会话历史 + 本轮输入」"""
    messages: List[BaseMessage] = [SystemMessage(content=build_system_prompt())]

    history_limit = 10
    if context and isinstance(context.get("history_limit"), int):
        history_limit = max(0, min(context["history_limit"], 50))
    messages.extend(
        await _load_history(
            conversation_id=conversation_id,
            limit=history_limit,
            exclude_message_id=exclude_message_id,
        )
    )
    messages.append(HumanMessage(content=user_message))
    return messages


def _build_result(messages: List[BaseMessage], collector: Any) -> dict:
    """把 Agent 的最终消息与收集器结果整理成接口返回结构"""
    response_text = _final_text(messages)
    if not response_text:
        response_text = "抱歉，我暂时无法生成有效回复，请稍后重试。"

    return {
        "response": response_text,
        "intent": None,
        "suggested_actions": build_suggested_actions(response_text),
        "weather_info": collector.get("weather_info") if collector else None,
        "tool_calls": collector.calls if collector else [],
        "itinerary": None,
    }


async def run_travel_agent(
    user_id: str,
    user_message: str,
    context: Optional[dict] = None,
    conversation_id: Optional[str] = None,
    exclude_message_id: Optional[str] = None,
) -> dict:
    """运行旅行规划 Agent（一次性返回，不推送中间过程）

    Args:
        user_id: 用户 ID
        user_message: 用户消息
        context: 上下文（可选，用于注入历史等）
        conversation_id: 当前会话 ID（用于加载该会话的历史上下文）
        exclude_message_id: 本轮用户消息已入库的 id，加载历史时排除，避免重复注入

    Returns:
        包含 response / weather_info / tool_calls 等字段的结果
    """
    logger.info(f"🚀 [Agent] 开始处理: {user_message[:50]}...")

    # 结构化结果收集器（天气卡片等）
    collector = start_collector()

    # 1) 严格校验 LLM 配置：缺 Key 直接给出明确指引，不静默降级
    try:
        check_llm_config()
    except LLMConfigError as e:
        logger.error(f"❌ LLM 配置错误: {e}")
        return _error_result(str(e), collector)

    # 2) 组装消息（系统提示 + 历史 + 本轮输入）
    messages = await _prepare_messages(
        user_message, context, conversation_id, exclude_message_id
    )

    # 3) 运行 Agent
    initial_state: Dict[str, Any] = {
        "messages": messages,
        "user_id": user_id,
        "user_message": user_message,
        "response": None,
        "suggested_actions": DEFAULT_ACTIONS,
        "error": None,
    }

    try:
        agent = get_travel_agent()
        result = await agent.ainvoke(
            initial_state,
            config={"recursion_limit": MAX_TOOL_ROUNDS * 2 + 2},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("❌ Agent 运行失败")
        return _error_result(f"Agent 运行失败：{type(e).__name__}: {e}", collector)

    return _build_result(result.get("messages", []), collector)


# ---------------------------------------------------------------- 流式执行

# 生产者结束的信号（None 也可能是合法事件，因此用独立哨兵）
_STREAM_END = object()


def _tool_message_failure(message: ToolMessage) -> Tuple[bool, str]:
    """判断工具消息是否代表失败，并取出给用户看的原因

    失败信息由 `format_tool_error` 生成，统一以「工具「X」调用失败：」开头，
    配置缺失则提示「由于配置缺失…」，据此识别即可，无需依赖特定版本字段。
    """
    content = message.content
    if not isinstance(content, str):
        content = str(content)

    status = getattr(message, "status", None)
    if status == "error" or content.startswith("工具「") and "调用失败" in content[:80]:
        return True, _first_line(content)
    if "由于配置缺失" in content[:40]:
        return True, _first_line(content)
    return False, ""


def _first_line(text: str, limit: int = 120) -> str:
    """取首行并截断，用于界面上的短提示"""
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line[:limit]


def _events_from_update(
    node: str,
    update: Any,
    pending: Dict[str, Dict[str, Any]],
    captured: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """把一次 LangGraph 节点更新翻译成进度事件

    - `agent` 节点产出 AI 消息：带 tool_calls 说明模型决定调用工具；
      不带则说明模型开始写最终回复。
    - `tools` 节点产出工具消息：与先前记录的 tool_start 配对，算出耗时。
    """
    events: List[Dict[str, Any]] = []
    if not isinstance(update, dict):
        return events

    messages = update.get("messages") or []
    if not isinstance(messages, list):
        return events

    for message in messages:
        # 累计消息，最后据此取最终回复（updates 模式只给增量）
        captured.setdefault("messages", []).append(message)

        if isinstance(message, ToolMessage):
            call_id = getattr(message, "tool_call_id", "") or ""
            started = pending.pop(call_id, None)
            name = getattr(message, "name", "") or (started or {}).get("name", "")
            info = tool_display(name)
            failed, reason = _tool_message_failure(message)
            duration_ms = 0
            if started:
                duration_ms = int((time.monotonic() - started["at"]) * 1000)
            events.append(
                {
                    "type": "tool_end",
                    "call_id": call_id,
                    "ok": not failed,
                    "duration_ms": duration_ms,
                    "error": reason,
                    "summary": (started or {}).get("summary", ""),
                    **info,
                }
            )
            continue

        if isinstance(message, AIMessage):
            calls = getattr(message, "tool_calls", None) or []
            if not calls:
                events.append(stage("正在整理行程内容", "writing"))
                continue
            for call in calls:
                name = (call or {}).get("name", "")
                args = (call or {}).get("args") or {}
                call_id = (call or {}).get("id", "") or ""
                info = tool_display(name)
                summary = describe_args(name, args)
                pending[call_id] = {
                    "name": name,
                    "summary": summary,
                    "at": time.monotonic(),
                }
                events.append(
                    {
                        "type": "tool_start",
                        "call_id": call_id,
                        "summary": summary,
                        **info,
                    }
                )

    return events


async def run_travel_agent_stream(
    user_id: str,
    user_message: str,
    context: Optional[dict] = None,
    conversation_id: Optional[str] = None,
    exclude_message_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """运行 Agent 并逐步产出执行过程事件

    事件类型见 `app.agent.progress`：stage / tool_start / tool_end / retry，
    最后一个事件固定为 `{"type": "done", "result": {...}}`（结构与非流式一致），
    失败时为 `{"type": "error", "text": "..."}` 后接 done。

    这里用「生产者任务 + 事件队列」而不是直接 `async for` 图更新，是因为
    工具内部的重试事件（`notify_retry`）与图更新来自两个来源：前者在退避等待
    期间就会产生，必须能立刻推给前端，而不是等下一个图事件到达才被带出来。
    """
    logger.info(f"🚀 [Agent/stream] 开始处理: {user_message[:50]}...")

    collector = start_collector()
    queue: "asyncio.Queue" = asyncio.Queue()
    start_progress(queue)

    try:
        check_llm_config()
    except LLMConfigError as e:
        logger.error(f"❌ LLM 配置错误: {e}")
        yield {"type": "error", "text": str(e)}
        yield {"type": "done", "result": _error_result(str(e), collector)}
        return

    yield stage("正在读取对话上下文", "context")
    messages = await _prepare_messages(
        user_message, context, conversation_id, exclude_message_id
    )

    initial_state: Dict[str, Any] = {
        "messages": messages,
        "user_id": user_id,
        "user_message": user_message,
        "response": None,
        "suggested_actions": DEFAULT_ACTIONS,
        "error": None,
    }

    captured: Dict[str, Any] = {"messages": []}
    pending: Dict[str, Dict[str, Any]] = {}
    failure: Dict[str, str] = {}

    async def _produce() -> None:
        try:
            agent = get_travel_agent()
            async for chunk in agent.astream(
                initial_state,
                config={"recursion_limit": MAX_TOOL_ROUNDS * 2 + 2},
                stream_mode="updates",
            ):
                for node, update in (chunk or {}).items():
                    for event in _events_from_update(node, update, pending, captured):
                        await queue.put(event)
        except Exception as e:  # noqa: BLE001 - 失败也要让前端看到原因
            logger.exception("❌ Agent 运行失败")
            failure["text"] = f"Agent 运行失败：{type(e).__name__}: {e}"
        finally:
            await queue.put(_STREAM_END)

    yield stage("正在理解你的需求", "thinking")

    task = asyncio.create_task(_produce())
    try:
        while True:
            event = await queue.get()
            if event is _STREAM_END:
                break
            yield event
    finally:
        # 客户端中途断开时不要把后台任务留在那里继续跑
        if not task.done():
            task.cancel()
    # 生产者的异常已在内部捕获，这里等待它收尾即可
    await asyncio.gather(task, return_exceptions=True)

    if failure:
        yield {"type": "error", "text": failure["text"]}
        yield {
            "type": "done",
            "result": _error_result(failure["text"], collector),
        }
        return

    yield {"type": "done", "result": _build_result(captured["messages"], collector)}


def _error_result(message: str, collector: Any) -> dict:
    """构造配置/运行错误的结果（明确报错，不返回任何伪造数据）"""
    return {
        "response": f"⚠ 无法完成查询：{message}",
        "intent": None,
        "suggested_actions": [],
        "weather_info": collector.get("weather_info") if collector else None,
        "tool_calls": collector.calls if collector else [],
        "itinerary": None,
    }
