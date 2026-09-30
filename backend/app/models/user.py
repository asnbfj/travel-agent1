"""用户数据模型"""
from sqlalchemy import Column, String, DateTime, JSON
# 跨数据库兼容的 UUID 类型：PostgreSQL 使用原生 UUID，SQLite 使用 CHAR(32)
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base


class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500))
    preferences = Column(JSON, default=dict)
    risk_level = Column(String(20), default="moderate")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    trips = relationship("Trip", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}: {self.email}>"
