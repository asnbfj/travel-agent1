"""行程 API 路由"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.trip import (
    PlanExtractRequest,
    PlanExtractResponse,
    TripCreate,
    TripFromPlanCreate,
    TripUpdate,
    TripResponse,
)
from app.services.plan_extract import infer_trip_fields
from app.services.trip_service import TripService
from app.utils.auth import get_current_user
import logging
from datetime import datetime

router = APIRouter(prefix="/api/v1/trips", tags=["行程"])
logger = logging.getLogger(__name__)
trip_service = TripService()


@router.get("", response_model=List[TripResponse])
async def list_trips(
    status_filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的行程列表"""
    trips = await trip_service.list_trips(
        user_id=str(current_user.id),
        status=status_filter,
        limit=limit,
        offset=offset,
        db=db,
    )
    return [trip_service.trip_to_dict(t) for t in trips]


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    payload: TripCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建行程"""
    trip = await trip_service.create_trip(
        user_id=str(current_user.id),
        data=payload.model_dump(),
        db=db,
    )
    return trip_service.trip_to_dict(trip)


@router.post("/plan/extract", response_model=PlanExtractResponse)
async def extract_plan_fields(
    payload: PlanExtractRequest,
    current_user: User = Depends(get_current_user),
):
    """从 AI 生成的行程中推断行程字段（供「保存到我的行程」弹窗预填）

    只是推断，不落库。用户在弹窗里确认或修改后再调用 `/from-plan`。
    """
    return infer_trip_fields(
        content=payload.content,
        weather_info=payload.weather_info,
        tool_calls=payload.tool_calls,
        user_message=payload.user_message,
    )


@router.post("/from-plan", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip_from_plan(
    payload: TripFromPlanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """把 AI 生成的行程保存为「我的行程」

    创建 Trip 的同时写入 `generated_plan`（正文 + 天气 + 原始提问），
    因此行程详情页能直接展示 AI 规划内容与天气卡片。
    """
    trip = await trip_service.create_trip(
        user_id=str(current_user.id),
        data=payload.model_dump(exclude={"content", "weather_info", "source_message"}),
        db=db,
    )
    plan = {
        "content": payload.content,
        "weather_info": payload.weather_info,
        "source_message": payload.source_message,
        "generated_at": datetime.utcnow().isoformat(),
    }
    trip = await trip_service.save_generated_plan(trip, plan, db)
    logger.info("📌 保存 AI 行程到我的行程: %s", trip.title)
    return trip_service.trip_to_dict(trip)


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取行程详情"""
    trip = await trip_service.get_trip(trip_id, str(current_user.id), db)
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")
    return trip_service.trip_to_dict(trip)


@router.put("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: str,
    payload: TripUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新行程"""
    trip = await trip_service.get_trip(trip_id, str(current_user.id), db)
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")
    updated = await trip_service.update_trip(trip, payload.model_dump(exclude_unset=True), db)
    return trip_service.trip_to_dict(updated)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除行程"""
    trip = await trip_service.get_trip(trip_id, str(current_user.id), db)
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")
    await trip_service.delete_trip(trip, db)
    return None
