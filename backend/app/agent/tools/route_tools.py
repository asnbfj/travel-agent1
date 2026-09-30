"""路线规划工具（LangChain Tool）

数据来源：高德地图路径规划（驾车 / 步行 / 骑行 / 公共交通），真实距离与耗时。
"""
import json
import logging

from langchain_core.tools import tool

from app.agent.tools.amap_client import AmapClient
from app.agent.tools.collector import collect

logger = logging.getLogger(__name__)


@tool("plan_route")
async def plan_route(origin: str, destination: str, mode: str = "driving", city: str = "") -> str:
    """规划两个地点之间的路线，返回真实距离、预计耗时与详细分段（数据来源：高德地图）。

    当用户询问「从 A 到 B 怎么走」「景点之间有多远」「需要多久」时调用。
    支持直接传地名（会自动解析坐标），也支持传「经度,纬度」。

    Args:
        origin: 起点，例如「北海站」或「109.119,21.473」
        destination: 终点，例如「涠洲岛」或「109.118,21.045」
        mode: 出行方式，可选 driving（驾车）/ walking（步行）/ bicycling（骑行）/ transit（公交地铁）
        city: 公交/地铁规划时必填的城市名，例如「北海」
    """
    client = AmapClient()
    route = await client.plan_route(origin=origin, destination=destination, mode=mode, city=city or None)

    collect("route", route)

    mode_label = {
        "driving": "驾车",
        "walking": "步行",
        "bicycling": "骑行",
        "transit": "公共交通",
    }.get(route["mode"], route["mode"])

    lines = [
        f"{route['origin']} → {route['destination']}（{mode_label}，高德地图实时规划）",
        f"总距离：{route['distance_km']} km",
        f"预计耗时：{route['duration_minutes']} 分钟",
    ]
    if route.get("toll"):
        lines.append(f"过路费：约 {route['toll']} 元")
    if route.get("traffic_lights"):
        lines.append(f"红绿灯：{route['traffic_lights']} 个")

    if route.get("options"):
        lines.append("可选方案：")
        for index, option in enumerate(route["options"], 1):
            segments = " → ".join(option.get("segments") or []) or "详见高德"
            lines.append(
                f"  方案{index}：{option['duration_minutes']}分钟 / {option['distance_km']}km"
                f" / 票价{option.get('cost', 0)}元 | {segments}"
            )
    elif route.get("steps"):
        lines.append("详细分段：")
        for step in route["steps"]:
            lines.append(f"  - {step['instruction']}（{step['distance_km']}km / {step['duration_minutes']}分钟）")

    return json.dumps({"text": "\n".join(lines)}, ensure_ascii=False)


__all__ = ["plan_route"]
