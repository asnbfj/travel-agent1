"""酒店查询工具（LangChain Tool）

数据来源：**博查 AI 搜索（联网检索）**（不使用高德 POI）。

⚠ 能力边界（已在工具描述与返回中明确告知模型）：
联网检索只能拿到公开的酒店介绍、口碑与参考价格，
**无法完成真实的下单预订**（实时房态与交易需要 OTA 或企业级接口资质）。

缺 Key 或检索失败会抛出明确异常，不返回任何模拟数据。
"""
import json
import logging

from langchain_core.tools import tool

from app.agent.tools.bocha_client import BochaClient
from app.agent.tools.collector import collect

logger = logging.getLogger(__name__)

_BOUNDARY_NOTE = (
    "说明：以上为联网检索到的公开酒店信息（含口碑与参考价格），"
    "不含实时房态与在线下单能力，实际预订请通过酒店官方渠道或 OTA 平台完成。"
)


@tool("search_hotels")
async def search_hotels(city: str, keyword: str = "", limit: int = 8) -> str:
    """联网搜索指定城市的酒店、民宿、宾馆等住宿信息与口碑价格（数据来源：博查 AI 搜索）。

    当用户需要住宿推荐、酒店位置、价格参考时调用。
    注意：只能查询信息，无法完成实际预订下单。

    Args:
        city: 城市名称，例如「北海」「丽江」
        keyword: 可选关键词，例如「海景」「民宿」「亲子」「市中心」；留空返回该城市住宿推荐
        limit: 返回条数，默认 8，最大 50
    """
    client = BochaClient()
    result = await client.search_hotels(city=city, keyword=keyword, limit=limit)

    collect("hotels", {"city": city, "answer": result["answer"], "sources": result["sources"]})

    return json.dumps(
        {
            "city": city,
            "text": result["text"],
            "sources": result["sources"],
            "note": _BOUNDARY_NOTE,
        },
        ensure_ascii=False,
    )


__all__ = ["search_hotels"]
