"""Agent 工具集（线上模式）

共 4 个真实工具，覆盖用户需求：
1. get_weather        高德地图        天气预报（结构化逐日预报）
2. search_attractions 博查 AI 搜索   景点 / 必玩地点 / 游玩攻略
3. search_hotels      博查 AI 搜索   酒店 / 住宿 / 口碑价格
4. plan_route         高德地图        路线规划

所有工具均实时调用线上 API，缺 Key 或调用失败会抛出明确异常，
不存在任何模拟 / 占位数据。
"""
from typing import List
import logging

from langchain_core.tools import BaseTool, StructuredTool

from app.agent.tools.weather_tools import get_weather
from app.agent.tools.spot_tools import search_attractions
from app.agent.tools.booking_tools import search_hotels
from app.agent.tools.route_tools import plan_route
from app.agent.tools.amap_client import AmapClient
from app.agent.tools.bocha_client import BochaClient
from app.agent.tools.errors import ToolConfigError, ToolCallError, format_tool_error
from app.agent.tools.collector import (
    start_collector,
    get_collector,
    collect,
    collect_call,
)

# 原始工具清单
ALL_TOOLS: List[BaseTool] = [
    get_weather,
    search_attractions,
    search_hotels,
    plan_route,
]

logger = logging.getLogger(__name__)


def _guard(tool: BaseTool) -> BaseTool:
    """把工具包装成「永不抛异常」版本

    多个工具会被 ToolNode 并行执行（asyncio.gather）。若在节点级别捕获异常，
    一个工具的错误会被错误地套用到同批次所有工具上（例如把「缺高德 Key」
    报成天气工具的错误）。因此必须在**单个工具**层面捕获。

    另外，配置类错误（缺 API Key）在本次请求内重试也不可能成功，
    这里会直接短路，避免模型反复重试浪费数十秒。
    """

    async def _run(**kwargs) -> str:
        collector = get_collector()

        # 已知本次请求内该工具不可用（缺 Key 等），直接短路
        if collector is not None and collector.is_unavailable(tool.name):
            logger.warning(f"⏭ 跳过重复调用不可用的工具「{tool.name}」")
            return (
                f"工具「{tool.name}」由于配置缺失，本次会话内无法使用，已跳过重复调用。"
                f"请直接向用户如实说明该功能暂时不可用，不要再次调用本工具。"
            )

        try:
            return await tool.ainvoke(kwargs)
        except ToolConfigError as e:
            # 配置类错误：标记为本次请求内不可用
            if collector is not None:
                collector.mark_unavailable(tool.name)
            logger.error(f"❌ 工具「{tool.name}」配置缺失: {e}")
            return format_tool_error(tool.name, e)
        except Exception as e:  # noqa: BLE001 - 兜住所有工具异常，转为可读文本
            logger.error(f"❌ 工具「{tool.name}」调用失败: {type(e).__name__}: {e}")
            return format_tool_error(tool.name, e)

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=_run,
        response_format="content",
    )


# 供 Agent 绑定的工具清单（已逐个做异常兜底）
SAFE_TOOLS: List[BaseTool] = [_guard(t) for t in ALL_TOOLS]

__all__ = [
    "get_weather",
    "search_attractions",
    "search_hotels",
    "plan_route",
    "ALL_TOOLS",
    "SAFE_TOOLS",
    "AmapClient",
    "BochaClient",
    "ToolConfigError",
    "ToolCallError",
    "format_tool_error",
    "start_collector",
    "get_collector",
    "collect",
    "collect_call",
]
