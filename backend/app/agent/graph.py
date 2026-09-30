"""LangGraph Agent 构建（tool-calling / ReAct 循环）

架构：模型绑定 4 个真实工具，由模型自主决定调用哪些工具、调用几轮。
      call_model -> (有 tool_calls?) -> tools -> call_model -> ... -> END

已移除原固定流水线与 RAG 检索。
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import tools_condition

from app.agent.state import AgentState
from app.agent.nodes import build_system_prompt, call_model, build_tool_node
from app.agent.tools import ALL_TOOLS, start_collector
from app.llm.client import check_llm_config, LLMConfigError
from app.config import get_settings
import logging

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


async def _load_history(user_id: str, limit: int = 10) -> List[BaseMessage]:
    """加载最近对话历史，转换为 LangChain 消息"""
    try:
        from app.agent.memory import get_conversation_history

        records = await get_conversation_history(user_id=user_id, limit=limit)
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


async def run_travel_agent(
    user_id: str,
    user_message: str,
    context: Optional[dict] = None,
) -> dict:
    """运行旅行规划 Agent

    Args:
        user_id: 用户 ID
        user_message: 用户消息
        context: 上下文（可选，用于注入历史等）

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
    messages: List[BaseMessage] = [SystemMessage(content=build_system_prompt())]

    history_limit = 10
    if context and isinstance(context.get("history_limit"), int):
        history_limit = max(0, min(context["history_limit"], 50))
    messages.extend(await _load_history(user_id, limit=history_limit))

    messages.append(HumanMessage(content=user_message))

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

    response_text = _final_text(result.get("messages", []))
    if not response_text:
        response_text = "抱歉，我暂时无法生成有效回复，请稍后重试。"

    return {
        "response": response_text,
        "intent": None,
        "suggested_actions": build_suggested_actions(response_text),
        "weather_info": collector.get("weather_info"),
        "tool_calls": collector.calls,
        "itinerary": None,
    }


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
