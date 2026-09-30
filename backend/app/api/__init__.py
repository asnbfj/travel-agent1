"""API 路由"""
from fastapi import APIRouter

from app.api import auth, trips, agent

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(trips.router)
api_router.include_router(agent.router)

__all__ = ["api_router"]
