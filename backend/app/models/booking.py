"""预订数据模型"""
from sqlalchemy import Column, String, DateTime, Integer, JSON, ForeignKey, DECIMAL
# 跨数据库兼容的 UUID 类型：PostgreSQL 使用原生 UUID，SQLite 使用 CHAR(32)
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base


class Booking(Base):
    """预订模型"""
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False, index=True)
    type = Column(String(20), nullable=False)  # flight / hotel / ticket / train
    provider = Column(String(100))  # 供应商
    reference_no = Column(String(100))  # 预订编号
    title = Column(String(200))
    details = Column(JSON, default=dict)  # 预订详情
    price = Column(DECIMAL(10, 2), default=0)
    quantity = Column(Integer, default=1)
    status = Column(String(20), default="pending")  # pending / confirmed / cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    trip = relationship("Trip", back_populates="bookings")

    def __repr__(self):
        return f"<Booking {self.type}: {self.title}>"
