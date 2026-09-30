"""行程相关 Pydantic 模型"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from datetime import date, datetime
import uuid


class ItinerarySpotSchema(BaseModel):
    """行程景点"""
    id: uuid.UUID
    order_index: int
    name: Optional[str] = None
    category: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_minutes: int = 120
    transport_to_next: Optional[str] = None
    estimated_cost: int = 0
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ItineraryDaySchema(BaseModel):
    """每日行程"""
    id: uuid.UUID
    day_number: int
    date: date
    theme: Optional[str] = None
    summary: Optional[str] = None
    weather_info: Optional[Dict[str, Any]] = None
    spots: List[ItinerarySpotSchema] = []

    model_config = {"from_attributes": True}


class TripCreate(BaseModel):
    """创建行程请求"""
    title: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(..., min_length=1, max_length=200)
    start_date: date
    end_date: date
    budget: int = Field(default=0, ge=0)
    travelers: int = Field(default=1, ge=1)
    requirements: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TripUpdate(BaseModel):
    """更新行程请求"""
    title: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[int] = None
    travelers: Optional[int] = None
    requirements: Optional[Dict[str, Any]] = None


class PlanExtractRequest(BaseModel):
    """行程字段推断请求

    用于「保存到我的行程」弹窗的**预填**：把 AI 回复正文、天气卡片、
    工具调用记录与用户原话交给服务端推断出最可能的目的地/天数/日期等。
    """
    content: str = Field(..., min_length=1, max_length=100_000, description="AI 回复的 Markdown 正文")
    weather_info: Optional[Dict[str, Any]] = Field(default=None, description="天气卡片数据")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="本次工具调用记录")
    user_message: Optional[str] = Field(default=None, max_length=2000, description="用户原始提问")


class PlanExtractResponse(BaseModel):
    """行程字段推断结果"""
    title: str
    destination: str = Field(default="", description="推断不出时为空串，由用户补填")
    start_date: date
    end_date: date
    budget: int = 0
    travelers: int = 1
    days_count: int = Field(default=1, ge=1)


class TripFromPlanCreate(TripCreate):
    """由 AI 行程创建行程（同时保存规划正文与天气数据）"""
    content: str = Field(..., min_length=1, max_length=100_000, description="AI 生成的 Markdown 行程")
    weather_info: Optional[Dict[str, Any]] = Field(default=None, description="天气卡片数据")
    source_message: Optional[str] = Field(default=None, max_length=2000, description="用户原始提问")

    @model_validator(mode="after")
    def check_date_order(self):
        if self.end_date < self.start_date:
            raise ValueError("返回日期不能早于出发日期")
        return self


class TripResponse(BaseModel):
    """行程响应"""
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    destination: str
    start_date: date
    end_date: date
    budget: int = 0
    travelers: int = 1
    status: str = "planning"
    requirements: Dict[str, Any] = {}
    generated_plan: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TripDetailResponse(TripResponse):
    """行程详情响应（含每日安排）"""
    days: List[ItineraryDaySchema] = []
