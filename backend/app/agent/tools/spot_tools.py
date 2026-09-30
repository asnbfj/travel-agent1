"""景点搜索工具（LangChain Tool）

数据来源：**博查 AI 搜索（联网检索）**（不使用高德 POI）。

联网检索的好处是能拿到「必玩 / 必去 / 攻略」这类主观推荐类信息，
这是 POI 列表接口给不了的；代价是没有结构化坐标与评分，
因此行程规划时请把**景点名称**交给 plan_route（高德会自行地理编码）。

缺 Key 或检索失败会抛出明确异常，不返回任何模拟数据。
"""
import json
import logging

from langchain_core.tools import tool

from app.agent.tools.bocha_client import BochaClient
from app.agent.tools.collector import collect

logger = logging.getLogger(__name__)


@tool("search_attractions")
async def search_attractions(city: str, keyword: str = "", limit: int = 8) -> str:
    """联网搜索指定城市及其周边的必去景点、必玩地点、游玩攻略与推荐（数据来源：博查 AI 搜索）。

    当用户询问某地有什么好玩的地方、必去/必玩景点、景点推荐、游玩攻略时调用。

    Args:
        city: 城市名称，例如「北海」「杭州」
        keyword: 可选的关键词/主题，例如「海滩」「古镇」「博物馆」「亲子」「小众」；留空则检索该城市必去景点
        limit: 返回条数，默认 8，最大 50
    """
    client = BochaClient()
    result = await client.search_attractions(city=city, keyword=keyword, limit=limit)

    collect(
        "attractions",
        {"city": city, "answer": result["answer"], "sources": result["sources"]},
    )

    return json.dumps(
        {
            "city": city,
            "text": result["text"],
            "sources": result["sources"],
            "note": (
                "以上为联网检索到的公开内容（含游记/攻略等），"
                "门票价格、开放时间等信息可能变动，请以官方渠道为准。"
            ),
        },
        ensure_ascii=False,
    )


__all__ = ["search_attractions"]
