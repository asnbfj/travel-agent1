"""行程业务逻辑"""
from typing import List, Dict, Any, Optional
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.trip import Trip, ItineraryDay, ItinerarySpot
from app.utils.helpers import to_uuid
import logging
import uuid

logger = logging.getLogger(__name__)


class TripService:
    """行程服务"""

    async def create_trip(self, user_id: str, data: Dict[str, Any], db: AsyncSession) -> Trip:
        """创建行程"""
        trip = Trip(
            user_id=to_uuid(user_id),
            title=data.get("title"),
            destination=data.get("destination"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            budget=data.get("budget", 0),
            travelers=data.get("travelers", 1),
            requirements=data.get("requirements", {}) or {},
        )
        db.add(trip)
        await db.commit()
        await db.refresh(trip)
        logger.info(f"✅ 创建行程: {trip.title}")
        return trip

    async def get_trip(
        self,
        trip_id: str,
        user_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Trip]:
        """获取单个行程"""
        stmt = select(Trip).where(Trip.id == to_uuid(trip_id))
        if user_id:
            stmt = stmt.where(Trip.user_id == to_uuid(user_id))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_trips(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        db: Optional[AsyncSession] = None,
    ) -> List[Trip]:
        """列出用户的行程"""
        stmt = select(Trip).where(Trip.user_id == to_uuid(user_id))
        if status:
            stmt = stmt.where(Trip.status == status)
        stmt = stmt.order_by(Trip.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_trip(
        self,
        trip: Trip,
        updates: Dict[str, Any],
        db: AsyncSession,
    ) -> Trip:
        """更新行程"""
        for key, value in updates.items():
            if value is not None and hasattr(trip, key):
                setattr(trip, key, value)
        await db.commit()
        await db.refresh(trip)
        return trip

    async def delete_trip(self, trip: Trip, db: AsyncSession) -> None:
        """删除行程"""
        await db.delete(trip)
        await db.commit()
        logger.info(f"🗑 删除行程: {trip.id}")

    async def save_generated_plan(
        self,
        trip: Trip,
        plan: Dict[str, Any],
        db: AsyncSession,
    ) -> Trip:
        """保存 AI 生成的行程方案"""
        trip.generated_plan = plan
        await db.commit()
        await db.refresh(trip)
        return trip

    def trip_to_dict(self, trip: Trip) -> Dict[str, Any]:
        """行程转字典"""
        return {
            "id": str(trip.id),
            "user_id": str(trip.user_id),
            "title": trip.title,
            "destination": trip.destination,
            "start_date": trip.start_date,
            "end_date": trip.end_date,
            "budget": trip.budget,
            "travelers": trip.travelers,
            "status": trip.status,
            "requirements": trip.requirements or {},
            "generated_plan": trip.generated_plan,
            "created_at": trip.created_at,
            "updated_at": trip.updated_at,
        }
