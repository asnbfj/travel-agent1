"""用户相关 Pydantic 模型"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserUpdate(BaseModel):
    """用户信息更新"""
    avatar_url: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None
    risk_level: Optional[str] = None


class UserResponse(BaseModel):
    """用户信息响应"""
    id: uuid.UUID
    username: str
    email: str
    avatar_url: Optional[str] = None
    preferences: Dict[str, Any] = {}
    risk_level: str = "moderate"
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """令牌响应"""
    access_token: str
    token_type: str = "bearer"
    user: Optional[UserResponse] = None


class TokenPayload(BaseModel):
    """令牌载荷"""
    sub: Optional[str] = None
    exp: Optional[int] = None
