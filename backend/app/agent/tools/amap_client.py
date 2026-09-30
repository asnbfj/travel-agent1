"""高德地图 Web 服务客户端

统一封装三件事：
1. 地理编码（地名 -> 经纬度 / adcode）
2. POI 搜索（景点、酒店等）
3. 路径规划（驾车 / 步行 / 公交）

所有方法在缺 Key 或接口报错时都会抛出明确异常，不返回任何模拟数据。
文档：https://lbs.amap.com/api/webservice/summary
"""
from typing import Optional, Dict, Any, List, Tuple
import asyncio
import logging
import time

import httpx

from app.config import get_settings
from app.agent.tools.errors import require_key, raise_for_http, raise_for_amap, ToolCallError
from app.agent.tools.retry import (
    RETRYABLE_STATUS_CODES,
    backoff_delay,
    describe_status_reason,
    retry_reason,
)
from app.agent.progress import notify_retry

logger = logging.getLogger(__name__)
settings = get_settings()

# 高德 POI 类型码
AMAP_TYPE_ATTRACTION = "110000"  # 风景名胜
AMAP_TYPE_HOTEL = "100000"       # 住宿服务

_MODE_PATH = {
    "driving": "/direction/driving",
    "walking": "/direction/walking",
    "bicycling": "/direction/bicycling",
    "transit": "/direction/transit/integrated",
}

# 高德天气接口
AMAP_WEATHER_PATH = "/weather/weatherInfo"
# 高德预报接口最多提供约 3~4 天
AMAP_WEATHER_MAX_DAYS = 4

# 高德 week 字段：1=周一 ... 7=周日
_AMAP_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 高德 QPS 超限的错误码
_AMAP_QPS_INFOCODES = {"10021", "10019", "10020", "10003", "10004"}
# 其中「配额用尽」重试也不会恢复（当天不会再放量），不该白等退避
_AMAP_QPS_NO_RETRY_INFOCODES = {"10003"}


def _is_qps_error(payload: Any) -> bool:
    """判断高德响应是否为 QPS 限流（这类错误值得退避重试）"""
    if not isinstance(payload, dict):
        return False
    if str(payload.get("status")) == "1":
        return False
    return str(payload.get("infocode", "")) in _AMAP_QPS_INFOCODES


def _is_retryable_qps_error(payload: Any) -> bool:
    """限流类错误中，重试真的可能有用的那些"""
    if not isinstance(payload, dict):
        return False
    return str(payload.get("infocode", "")) in (
        _AMAP_QPS_INFOCODES - _AMAP_QPS_NO_RETRY_INFOCODES
    )

# 城市级地名可接受的行政级别（高德 geocode 的 level 字段）
#
# 高德地理编码是**模糊匹配**，随手输入的字符串也可能被解析到某个乡镇/村庄。
# 实测：'东京' 会被解析成「广西贵港市平南县东京」（村庄），
# '不存在的地名XYZ' 会被解析成「内蒙古锡林郭勒盟正镶白旗星耀镇」（乡镇）。
# 若不校验，就会把完全另一个地方的天气当成用户要的城市返回——这属于错误数据。
_CITY_LEVELS = {"省", "市", "区县", "区", "县", "直辖市", "国家"}

# 这些级别说明是「城市内的具体地点」而非独立城市（可提示改用上级城市）
_POI_LEVELS = {"兴趣点", "住宅区", "风景名胜", "门牌号", "道路", "商务住宅", "地名地址信息"}


class _AmapRateLimiter:
    """同 Key 全局串行限速器

    高德按 Key 限 QPS，而 LangGraph 的 ToolNode 会用 asyncio.gather 并行执行工具
    （且每个 plan_route 内部还要额外做 2 次地理编码），瞬间并发很容易打出 10021。
    这里让所有高德请求共享一把锁并保持最小间隔，把尖峰摊平。
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(0.0, min_interval)
        self._lock = asyncio.Lock()
        self._last_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            idle = time.monotonic() - self._last_at
            wait = self._min_interval - idle
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_at = time.monotonic()


_rate_limiter = _AmapRateLimiter(getattr(settings, "AMAP_MIN_INTERVAL", 0.34))


class AmapClient:
    """高德地图客户端"""

    TOOL = "高德地图"

    def __init__(self) -> None:
        self.key: Optional[str] = settings.AMAP_API_KEY
        self.base_url: str = (settings.AMAP_BASE_URL or "https://restapi.amap.com/v3").rstrip("/")
        self.timeout: int = settings.AMAP_TIMEOUT
        self.qps_retry: int = getattr(settings, "AMAP_QPS_RETRY", 2)
        # 瞬时故障（超时 / 网络中断 / 5xx / 429）的重试次数
        self.transient_retry: int = getattr(settings, "AMAP_RETRY_ATTEMPTS", 3)
        self._retry_base: float = getattr(settings, "API_RETRY_BASE_DELAY", 0.8)
        self._retry_cap: float = getattr(settings, "API_RETRY_MAX_DELAY", 8.0)
        self._retry_jitter: float = getattr(settings, "API_RETRY_JITTER", 0.25)

    # ------------------------------------------------------------------ 底层
    def _require_key(self) -> str:
        return require_key(
            self.TOOL,
            self.key,
            "AMAP_API_KEY",
            "请到 https://console.amap.com/dev/key/app 申请「Web服务」类型的 Key 并填入 .env",
        )

    async def _sleep_before_retry(
        self, path: str, reason: str, attempt: int, total: int
    ) -> None:
        """退避等待，并把「即将重试」推给前端

        Args:
            attempt: 第几次重试（从 1 开始，用于日志与界面展示）
            total: 最多重试几次
        """
        delay = backoff_delay(attempt - 1, self._retry_base, self._retry_cap, self._retry_jitter)
        logger.warning(
            "⏳ 高德%s，%.1fs 后重试（第 %d/%d 次）：%s",
            reason,
            delay,
            attempt,
            total,
            path,
        )
        notify_retry(self.TOOL, attempt, total, delay, reason)
        await asyncio.sleep(delay)

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        key = self._require_key()
        query = {k: v for k, v in params.items() if v not in (None, "")}
        query["key"] = key
        url = f"{self.base_url}{path}"

        # QPS 限流与瞬时故障分开计数：成因不同，重试预算也不该互相挤占
        # （限流靠限速器慢慢摊平，网络抖动靠退避快速恢复）
        qps_left = self.qps_retry
        transient_left = self.transient_retry

        while True:
            # 每次请求前都过一遍全局限速器，把并发尖峰摊平
            await _rate_limiter.acquire()

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, params=query)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # 超时 / 连接被重置这类网络故障是典型瞬时错误，值得重试
                reason = retry_reason(e)
                if transient_left > 0:
                    transient_left -= 1
                    used = self.transient_retry - transient_left
                    await self._sleep_before_retry(path, reason, used, self.transient_retry)
                    continue
                if isinstance(e, httpx.TimeoutException):
                    raise ToolCallError(
                        self.TOOL,
                        f"请求超时（{self.timeout}s），已重试 {self.transient_retry} 次仍失败：{path}",
                    )
                raise ToolCallError(
                    self.TOOL,
                    f"网络错误，已重试 {self.transient_retry} 次仍失败：{e}",
                )

            # 5xx / 429 属瞬时故障；重试耗尽后再按普通错误抛出
            if response.status_code in RETRYABLE_STATUS_CODES:
                reason = describe_status_reason(response.status_code)
                if transient_left > 0:
                    transient_left -= 1
                    used = self.transient_retry - transient_left
                    await self._sleep_before_retry(path, reason, used, self.transient_retry)
                    continue
                raise_for_http(self.TOOL, response)

            raise_for_http(self.TOOL, response)
            try:
                payload = response.json()
            except ValueError:
                raise ToolCallError(self.TOOL, f"返回内容不是 JSON：{response.text[:200]}")

            # QPS 超限：退避后重试（高德这个错误通常是瞬时的）
            if _is_retryable_qps_error(payload) and qps_left > 0:
                qps_left -= 1
                used = self.qps_retry - qps_left
                await self._sleep_before_retry(
                    path,
                    f"QPS 超限（{payload.get('infocode')}）",
                    used,
                    self.qps_retry,
                )
                continue

            # 走到这里说明不可恢复（Key 无效 / 参数错误 / 配额用尽），直接报错
            raise_for_amap(self.TOOL, payload)
            return payload

    # -------------------------------------------------------------- 地理编码
    async def geocode(self, address: str, city: Optional[str] = None) -> Dict[str, Any]:
        """地名 -> 经纬度"""
        payload = await self._get("/geocode/geo", {"address": address, "city": city})
        geocodes = payload.get("geocodes") or []
        if not geocodes:
            raise ToolCallError(self.TOOL, f"无法解析地点「{address}」，请换一个更明确的地名")
        first = geocodes[0]
        location = first.get("location") or ""
        if "," not in location:
            raise ToolCallError(self.TOOL, f"地点「{address}」未返回有效坐标")
        lng, lat = location.split(",", 1)
        return {
            "address": first.get("formatted_address") or address,
            "city": first.get("city") or city or "",
            "adcode": first.get("adcode") or "",
            "province": first.get("province") or "",
            "district": first.get("district") or "",
            "lng": lng,
            "lat": lat,
            "location": location,
            "level": first.get("level") or "",
        }

    async def resolve_location(self, place: str, city: Optional[str] = None) -> str:
        """把地名解析成「经度,纬度」；已经是坐标则原样返回"""
        if place and "," in place:
            parts = place.split(",")
            if len(parts) == 2:
                try:
                    float(parts[0]); float(parts[1])
                    return place
                except ValueError:
                    pass
        info = await self.geocode(place, city=city)
        return info["location"]

    # --------------------------------------------------------------- POI 搜索
    async def search_poi(
        self,
        keywords: str,
        city: Optional[str] = None,
        typecode: Optional[str] = None,
        limit: int = 10,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """POI 关键字搜索（extensions=all 以拿到评分/人均等扩展字段）"""
        payload = await self._get(
            "/place/text",
            {
                "keywords": keywords,
                "city": city,
                "citylimit": "true" if city else None,
                "types": typecode,
                "offset": max(1, min(int(limit), 25)),
                "page": page,
                "extensions": "all",
            },
        )
        return self._normalize_pois(payload.get("pois") or [])

    @staticmethod
    def _normalize_pois(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把高德 POI 归一化成统一结构"""
        results: List[Dict[str, Any]] = []
        for poi in pois:
            if not isinstance(poi, dict):
                continue
            location = poi.get("location") or ""
            lng = lat = None
            if "," in location:
                lng, lat = location.split(",", 1)

            biz = poi.get("biz_ext") or {}
            if not isinstance(biz, dict):
                biz = {}

            raw_type = poi.get("type") or ""
            photos = [
                p.get("url")
                for p in (poi.get("photos") or [])
                if isinstance(p, dict) and p.get("url")
            ]

            results.append(
                {
                    "id": poi.get("id") or "",
                    "name": poi.get("name") or "",
                    "type": raw_type,
                    "category": raw_type.split(";")[-1] if raw_type else "",
                    "address": poi.get("address") if isinstance(poi.get("address"), str) else "",
                    "city": poi.get("cityname") or "",
                    "district": poi.get("adname") or "",
                    "province": poi.get("pname") or "",
                    "tel": poi.get("tel") if isinstance(poi.get("tel"), str) else "",
                    "lng": lng,
                    "lat": lat,
                    "location": location,
                    "rating": _to_float(biz.get("rating")),
                    "cost": _to_float(biz.get("cost")),
                    "open_time": biz.get("open_time") or "",
                    "photos": photos[:3],
                }
            )
        return results

    # --------------------------------------------------------------- 天气查询
    async def get_forecast(self, city: str, days: int = 3) -> Dict[str, Any]:
        """查询城市天气预报（extensions=all）

        高德天气接口要求 city 为 adcode，因此先用地理编码把城市名换成 adcode。
        若预报为空，则退化为实况天气（extensions=base）。
        """
        days = max(1, min(int(days), AMAP_WEATHER_MAX_DAYS))

        info = await self.geocode(city)
        _validate_city_match(city, info)

        adcode = info.get("adcode") or ""
        if not adcode:
            raise ToolCallError(self.TOOL, f"无法解析城市「{city}」的行政区划编码，请换一个更明确的城市名")

        payload = await self._get(
            AMAP_WEATHER_PATH,
            {"city": adcode, "extensions": "all"},
        )

        forecasts = payload.get("forecasts") or []
        report = forecasts[0] if forecasts and isinstance(forecasts[0], dict) else {}
        casts = report.get("casts") or []

        if casts:
            return {
                "city": city,
                "adcode": adcode,
                "province": info.get("province") or report.get("province") or "",
                "report_time": report.get("reporttime") or "",
                "casts": [
                    self._normalize_cast(item)
                    for item in casts[:days]
                    if isinstance(item, dict)
                ],
                "live": None,
                "kind": "forecast",
            }

        # 预报为空 -> 取实况天气兜底
        live = await self.get_live_weather(adcode)
        live["city"] = city
        live["province"] = info.get("province") or ""
        live["adcode"] = adcode
        return live

    async def get_live_weather(self, adcode: str) -> Dict[str, Any]:
        """实况天气（extensions=base）"""
        payload = await self._get(
            AMAP_WEATHER_PATH,
            {"city": adcode, "extensions": "base"},
        )

        lives = payload.get("lives") or []
        if not lives or not isinstance(lives[0], dict):
            raise ToolCallError(self.TOOL, "未查询到该城市的天气数据，请确认城市名是否正确")

        item = lives[0]
        return {
            "city": "",
            "adcode": item.get("adcode") or adcode,
            "province": item.get("province") or "",
            "report_time": item.get("reporttime") or "",
            "casts": [],
            "live": {
                "weather": item.get("weather") or "",
                "temperature": _to_float(item.get("temperature")),
                "wind_direction": item.get("winddirection") or "",
                "wind_power": item.get("windpower") or "",
                "humidity": _to_float(item.get("humidity")),
            },
            "kind": "live",
        }

    @staticmethod
    def _normalize_cast(item: Dict[str, Any]) -> Dict[str, Any]:
        """归一化高德单日预报"""
        week = str(item.get("week") or "")
        weekday = _AMAP_WEEKDAYS[int(week) - 1] if week.isdigit() and 1 <= int(week) <= 7 else ""

        day_weather = item.get("dayweather") or ""
        night_weather = item.get("nightweather") or ""
        # 白天与夜间天气不同（如「晴转多云」）时给出更完整描述
        weather = day_weather if day_weather == night_weather else f"{day_weather}转{night_weather}"

        day_wind = item.get("daywind") or ""
        day_power = item.get("daypower") or ""
        wind = f"{day_wind}风{day_power}级" if day_wind else ""

        return {
            "date": item.get("date") or "",
            "weekday": weekday,
            "weather": weather,
            "day_weather": day_weather,
            "night_weather": night_weather,
            "temp_high": _to_float(item.get("daytemp_float") or item.get("daytemp")),
            "temp_low": _to_float(item.get("nighttemp_float") or item.get("nighttemp")),
            "wind": wind,
        }

    # --------------------------------------------------------------- 路径规划
    async def plan_route(
        self,
        origin: str,
        destination: str,
        mode: str = "driving",
        city: Optional[str] = None,
    ) -> Dict[str, Any]:
        """路径规划，返回距离/耗时/分段"""
        mode = (mode or "driving").lower()
        if mode not in _MODE_PATH:
            raise ToolCallError(self.TOOL, f"不支持的出行方式「{mode}」，可选：driving / walking / bicycling / transit")

        origin_loc = await self.resolve_location(origin, city=city)
        dest_loc = await self.resolve_location(destination, city=city)

        params: Dict[str, Any] = {"origin": origin_loc, "destination": dest_loc, "extensions": "all"}
        if mode == "transit":
            params["city"] = city or ""
            params["cityd"] = city or ""

        payload = await self._get(_MODE_PATH[mode], params)
        route = payload.get("route") or {}

        if mode == "transit":
            return self._parse_transit(route, origin, destination, origin_loc, dest_loc)

        paths = route.get("paths") or []
        if not paths:
            raise ToolCallError(self.TOOL, f"未找到 {origin} → {destination} 的{mode}路线")
        path = paths[0]

        distance_m = _to_float(path.get("distance")) or 0.0
        duration_s = _to_float(path.get("duration")) or 0.0

        return {
            "mode": mode,
            "origin": origin,
            "destination": destination,
            "origin_location": origin_loc,
            "destination_location": dest_loc,
            "distance_km": round(distance_m / 1000, 2),
            "duration_minutes": int(duration_s / 60),
            "toll": _to_float(path.get("tolls")) or 0.0,
            "traffic_lights": int(_to_float(path.get("traffic_lights")) or 0),
            "steps": [
                {
                    "instruction": step.get("instruction") or "",
                    "road": step.get("road") or "",
                    "distance_km": round((_to_float(step.get("distance")) or 0.0) / 1000, 2),
                    "duration_minutes": int((_to_float(step.get("duration")) or 0.0) / 60),
                }
                for step in (path.get("steps") or [])[:20]
                if isinstance(step, dict)
            ],
        }

    @staticmethod
    def _parse_transit(
        route: Dict[str, Any],
        origin: str,
        destination: str,
        origin_loc: str,
        dest_loc: str,
    ) -> Dict[str, Any]:
        """解析公交/地铁方案"""
        transits = route.get("transits") or []
        if not transits:
            raise ToolCallError("高德地图", f"未找到 {origin} → {destination} 的公共交通路线")

        options: List[Dict[str, Any]] = []
        for transit in transits[:3]:
            if not isinstance(transit, dict):
                continue
            segments: List[str] = []
            for seg in transit.get("segments") or []:
                if not isinstance(seg, dict):
                    continue
                if seg.get("walking"):
                    walk = seg["walking"] or {}
                    if walk.get("distance"):
                        segments.append(f"步行{int(_to_float(walk.get('distance')) or 0)}米")
                bus = seg.get("bus") or {}
                for line in (bus.get("buslines") or []) if isinstance(bus, dict) else []:
                    if isinstance(line, dict) and line.get("name"):
                        segments.append(str(line["name"]))
                railway = seg.get("railway") or {}
                if isinstance(railway, dict) and railway.get("name"):
                    segments.append(str(railway["name"]))

            options.append(
                {
                    "duration_minutes": int((_to_float(transit.get("duration")) or 0.0) / 60),
                    "distance_km": round((_to_float(transit.get("distance")) or 0.0) / 1000, 2),
                    "cost": _to_float(transit.get("cost")) or 0.0,
                    "walking_distance_m": int(_to_float(transit.get("walking_distance")) or 0),
                    "segments": segments[:12],
                }
            )

        if not options:
            raise ToolCallError("高德地图", f"未找到 {origin} → {destination} 的公共交通路线")

        first = options[0]
        return {
            "mode": "transit",
            "origin": origin,
            "destination": destination,
            "origin_location": origin_loc,
            "destination_location": dest_loc,
            "distance_km": first["distance_km"],
            "duration_minutes": first["duration_minutes"],
            "options": options,
        }


def _validate_city_match(requested: str, info: Dict[str, Any]) -> None:
    """校验地理编码结果是否真的是「城市」，避免模糊匹配返回错误地方的天气

    只用于**城市级查询**（天气）。路径规划的 origin/destination 可能是景点、
    门牌号等（level 为「兴趣点」「门牌号」也属正常），因此不能做同样的限制。
    """
    level = (info.get("level") or "").strip()
    address = info.get("address") or ""
    requested = (requested or "").strip()

    if level and level not in _CITY_LEVELS:
        # 解析到了城市内的具体地点（景点/住宅区等）→ 提示改用上级城市查询
        parent = (info.get("city") or info.get("province") or "").strip()
        if level in _POI_LEVELS and parent and parent != requested:
            raise ToolCallError(
                AmapClient.TOOL,
                f"「{requested}」是「{parent}」下的具体地点（级别：{level}），"
                f"不是独立城市。高德天气按城市提供，请改用城市名「{parent}」查询",
            )
        raise ToolCallError(
            AmapClient.TOOL,
            f"无法把「{requested}」匹配到城市级地名（高德解析为「{address}」，级别为「{level}」）。"
            "高德天气接口只覆盖中国境内城市，请提供更明确的城市名；"
            "若是境外城市（如东京、巴黎），本接口无法提供天气",
        )

    # 解析结果里应包含用户给出的名称，避免模糊命中完全无关的城市
    if requested and requested not in address:
        raise ToolCallError(
            AmapClient.TOOL,
            f"无法把「{requested}」准确匹配到城市（高德解析结果为「{address}」）。请提供更明确的城市名",
        )


def _to_float(value: Any) -> Optional[float]:
    """高德很多数值以字符串返回，且空值用 [] 表示"""
    if value is None or value == "" or value == []:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
