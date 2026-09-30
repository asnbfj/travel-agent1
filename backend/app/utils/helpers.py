"""通用工具函数"""
from typing import Any, Optional
from datetime import datetime, date, timezone
import uuid
import json


def generate_uuid() -> str:
    """生成 UUID 字符串"""
    return str(uuid.uuid4())


def to_uuid(value: Any) -> Optional[uuid.UUID]:
    """将字符串安全转换为 uuid.UUID（非法输入返回 None）"""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def now_utc() -> datetime:
    """当前 UTC 时间"""
    return datetime.now(timezone.utc)


def format_date_range(start: Optional[date], end: Optional[date]) -> str:
    """格式化日期区间"""
    if not start or not end:
        return ""
    return f"{start.isoformat()} ~ {end.isoformat()}"


def safe_json_loads(text: str, default: Any = None) -> Any:
    """安全解析 JSON"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def truncate(text: Optional[str], length: int = 100) -> str:
    """截断文本"""
    if not text:
        return ""
    return text if len(text) <= length else text[:length] + "..."


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点球面距离（km）"""
    import math
    R = 6371
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
