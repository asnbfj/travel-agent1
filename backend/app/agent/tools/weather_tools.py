"""天气查询工具（LangChain Tool）

数据来源：**高德地图天气接口**（/v3/weather/weatherInfo）。

高德直接返回结构化预报（白天/夜间天气、最高/最低气温、风向风力），
因此无需再用大模型二次规整，天气卡片数据天然可靠、也不多花一次 LLM 调用。

缺 Key 或调用失败会抛出明确异常，不返回任何模拟数据。
"""
from datetime import date
from typing import Any, Dict, List
import json
import logging

from langchain_core.tools import tool

from app.agent.tools.amap_client import AmapClient
from app.agent.tools.collector import collect

logger = logging.getLogger(__name__)

# 天气现象 -> emoji（前端直接展示 day.icon）
_WEATHER_ICONS = [
    (("雷", "thunder"), "⛈"),
    (("雪", "snow"), "❄"),
    (("雾", "霾", "fog", "haze"), "🌫"),
    (("雨", "rain"), "🌧"),
    (("阴", "overcast"), "☁"),
    (("多云", "cloud"), "⛅"),
    (("晴", "clear", "sun"), "☀"),
]

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


@tool("get_weather")
async def get_weather(city: str, days: int = 3) -> str:
    """查询指定城市的天气预报（数据来源：高德地图天气接口）。

    当用户询问某地天气、或需要根据天气情况安排行程与携带物品时调用。

    Args:
        city: 城市名称，例如「北海」「三亚」「东京」
        days: 需要预报的天数，默认 3，最多 4 天（高德预报接口能力上限）
    """
    client = AmapClient()
    result = await client.get_forecast(city=city, days=days)

    if result["kind"] == "live":
        return _format_live(result)

    forecasts = _build_forecasts(result["casts"])
    payload: Dict[str, Any] = {
        "city": result["city"],
        "source": "高德地图",
        "report_time": result.get("report_time") or "",
        "forecasts": forecasts,
        "tips": _build_tips(forecasts),
    }
    collect("weather_info", payload)

    lines = [f"{result['city']} 天气预报（高德地图，发布时间 {payload['report_time'] or '未知'}）："]
    for day in forecasts:
        lines.append(
            f"- {day['date']} {day['weekday']} {day['weather']} "
            f"{_temp_text(day['temp_low'], day['temp_high'])}"
            + (f" 风:{day['wind']}" if day["wind"] else "")
        )
    if payload["tips"]:
        lines.append(f"出行建议：{payload['tips']}")
    if len(forecasts) < 4:
        lines.append(
            f"（高德天气接口最多提供约 4 天预报，当前返回 {len(forecasts)} 天，"
            f"更长周期的预报建议出行前再查一次。）"
        )

    return json.dumps(
        {
            "city": result["city"],
            "forecasts": forecasts,
            "tips": payload["tips"],
            "text": "\n".join(lines),
        },
        ensure_ascii=False,
    )


def _format_live(result: Dict[str, Any]) -> str:
    """实况天气兜底（预报为空时）"""
    live = result["live"] or {}
    weather = live.get("weather") or "未知"
    temperature = live.get("temperature")
    wind = f"{live.get('wind_direction', '')}风{live.get('wind_power', '')}级" if live.get("wind_direction") else ""

    text = (
        f"{result['city']} 当前实况天气（高德地图，发布时间 {result.get('report_time') or '未知'}）："
        f"{weather}"
        + (f"，气温 {int(temperature)}°C" if temperature is not None else "")
        + (f"，{wind}" if wind else "")
        + "。高德接口暂未返回逐日预报，如需多日预报请在出行前再次查询。"
    )

    # 实况也放进卡片：只有一天数据，前端会渲染成单张卡片
    collect(
        "weather_info",
        {
            "city": result["city"],
            "source": "高德地图",
            "report_time": result.get("report_time") or "",
            "forecasts": [
                {
                    "date": date.today().isoformat(),
                    "weekday": _WEEKDAYS[date.today().weekday()],
                    "weather": weather,
                    "icon": _to_icon(weather),
                    "temp_high": int(temperature) if temperature is not None else None,
                    "temp_low": None,
                    "wind": wind,
                    "pm25": None,
                }
            ],
            "tips": "",
        },
    )

    return json.dumps(
        {"city": result["city"], "forecasts": [], "text": text, "kind": "live"},
        ensure_ascii=False,
    )


def _build_forecasts(casts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把高德预报转成前端卡片契约结构"""
    forecasts: List[Dict[str, Any]] = []
    for item in casts:
        weather = item.get("weather") or ""
        forecasts.append(
            {
                "date": item.get("date") or "",
                "weekday": item.get("weekday") or _weekday_label(item.get("date") or ""),
                "weather": weather,
                "icon": _to_icon(weather),
                "temp_high": _round(item.get("temp_high")),
                "temp_low": _round(item.get("temp_low")),
                "wind": item.get("wind") or "",
                "pm25": None,
            }
        )
    return forecasts


def _round(value: Any):
    return None if value is None else int(round(value))


def _temp_text(low, high) -> str:
    if low is not None and high is not None:
        return f"{low}~{high}°C"
    if high is not None:
        return f"最高{high}°C"
    if low is not None:
        return f"最低{low}°C"
    return "温度未知"


def _weekday_label(date_str: str) -> str:
    try:
        return _WEEKDAYS[date.fromisoformat(date_str).weekday()]
    except (ValueError, TypeError):
        return ""


def _to_icon(weather: str) -> str:
    lowered = (weather or "").lower()
    for keywords, icon in _WEATHER_ICONS:
        if any(k in weather or k in lowered for k in keywords):
            return icon
    return "🌤"


def _build_tips(forecasts: List[Dict[str, Any]]) -> str:
    """根据预报生成出行建议"""
    tips: List[str] = []
    rainy = [f for f in forecasts if "雨" in (f.get("weather") or "")]
    if rainy:
        tips.append(f"行程中有 {len(rainy)} 天可能有雨，建议携带雨具。")

    highs = [f["temp_high"] for f in forecasts if f.get("temp_high") is not None]
    lows = [f["temp_low"] for f in forecasts if f.get("temp_low") is not None]
    if highs:
        avg_high = sum(highs) / len(highs)
        if avg_high > 30:
            tips.append("气温较高，注意防暑防晒，多补充水分。")
        elif avg_high < 15:
            tips.append("气温较低，建议携带外套和保暖衣物。")
    if highs and lows and (sum(highs) / len(highs) - sum(lows) / len(lows)) >= 10:
        tips.append("昼夜温差较大，建议洋葱式穿搭。")

    return " ".join(tips) if tips else "天气总体良好，适合出行。"


__all__ = ["get_weather", "AmapClient"]
