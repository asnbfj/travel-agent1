"""Agent 相关 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class AgentMessageRequest(BaseModel):
    """Agent 消息请求"""
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    context: Optional[Dict[str, Any]] = Field(default={}, description="上下文数据")


class AgentMessageResponse(BaseModel):
    """Agent 消息响应"""
    message: str = Field(..., description="AI 回复内容")
    intent: Optional[str] = Field(default=None, description="识别的意图")
    suggested_actions: List[str] = Field(default=[], description="建议的操作")
    itinerary: Optional[Dict[str, Any]] = Field(default=None, description="生成的行程")
    weather_info: Optional[Dict[str, Any]] = Field(default=None, description="天气信息（来自高德地图天气接口）")
    tool_calls: List[Dict[str, Any]] = Field(default=[], description="本次实际调用的线上工具")


class AgentPdfExportRequest(BaseModel):
    """行程 PDF 导出请求

    行程正文目前是 AI 生成的 Markdown（`AgentMessageResponse.message`），
    前端原样回传即可，服务端负责排版为 PDF。
    """
    content: str = Field(..., min_length=1, max_length=100_000, description="行程 Markdown 正文")
    title: Optional[str] = Field(default=None, max_length=200, description="文档标题（缺省时自动从正文提取）")
    destination: Optional[str] = Field(default=None, max_length=200, description="目的地")
    weather_info: Optional[Dict[str, Any]] = Field(
        default=None, description="天气卡片数据（来自高德地图，可选）"
    )


class ChatMessage(BaseModel):
    """对话消息"""
    id: str
    role: str  # "user" / "assistant"
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class ChatHistoryResponse(BaseModel):
    """对话历史响应"""
    messages: List[ChatMessage]
    total: int
    has_more: bool
