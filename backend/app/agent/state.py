"""Agent 状态定义"""
from typing import TypedDict, List, Optional, Annotated
from enum import Enum
from datetime import date

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class IntentType(str, Enum):
    """旅行意图类型"""
    TRIP_PLAN = "trip_plan"  # 行程规划
    SPOT_QUERY = "spot_query"  # 景点查询
    MODIFY_TRIP = "modify_trip"  # 修改行程
    BOOKING_QUERY = "booking_query"  # 预订查询
    WEATHER_QUERY = "weather_query"  # 天气查询
    BUDGET_QUERY = "budget_query"  # 预算查询
    TIPS_QUERY = "tips_query"  # 旅行 tips
    CHITCHAT = "chitchat"  # 闲聊


class TripStatus(str, Enum):
    """行程状态"""
    PLANNING = "planning"  # 规划中
    CONFIRMED = "confirmed"  # 已确认
    IN_PROGRESS = "in_progress"  # 旅途中
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class TravelStyle(str, Enum):
    """旅行风格"""
    RELAXED = "relaxed"  # 休闲度假
    ADVENTUROUS = "adventurous"  # 探险挑战
    CULTURAL = "cultural"  # 文化探索
    FAMILY = "family"  # 亲子游
    ROMANTIC = "romantic"  # 蜜月/情侣
    BUSINESS = "business"  # 商务旅行
    FOODIE = "foodie"  # 美食之旅
    PHOTOGRAPHY = "photography"  # 摄影采风


class AgentState(TypedDict, total=False):
    """Agent 状态（tool-calling 循环）

    采用 LangGraph 标准消息累加模式：``messages`` 由 ``add_messages``
    归并，LLM 与工具之间的多轮往返都记录在其中。
    """
    # 消息（含 System / Human / AI / Tool）
    messages: Annotated[List[BaseMessage], add_messages]

    # 会话标识
    user_id: str
    user_message: str

    # 输出
    response: Optional[str]
    suggested_actions: List[str]
    error: Optional[str]
