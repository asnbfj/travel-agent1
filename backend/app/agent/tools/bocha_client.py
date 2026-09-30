"""博查 AI 搜索客户端（https://open.bochaai.com）

用于「景点 / 必玩地点 / 酒店住宿」的联网搜索：
博查的 /v1/web-search 接口返回若干网页结果，每条含标题、链接、站点名、
发布时间与正文摘要（summary），这些文本会原样交给大模型组织成回答。

天气与路线规划不走这里（分别使用高德天气接口与高德路径规划接口）。

注意：博查**没有**「综合摘要（answer）」字段，因此这里的 `answer` 是由
排名靠前的来源摘要**节选拼接**而成，不是模型生成的内容。

缺 Key 或调用失败时抛出明确异常，不返回任何模拟数据。
接口文档：https://open.bochaai.com
"""
from datetime import date
from typing import Optional, Dict, Any, List
import asyncio
import logging

import httpx

from app.config import get_settings
from app.agent.tools.errors import require_key, ToolCallError
from app.agent.tools.retry import (
    RETRYABLE_STATUS_CODES,
    backoff_delay,
    describe_status_reason,
    retry_reason,
)
from app.agent.progress import notify_retry

logger = logging.getLogger(__name__)
settings = get_settings()

# 单条来源正文片段的最大长度（避免 prompt 过长）
_SNIPPET_LIMIT = 1200
# 合成「综合摘要」时最多取几条来源
_SUMMARY_SOURCES = 3
# 博查 count 参数上限
_BOCHA_MAX_COUNT = 50
# 合法的时间范围取值
_BOCHA_FRESHNESS = {"noLimit", "oneDay", "oneWeek", "oneMonth", "oneYear"}


def _build_query(city: str, keyword: str, category: str) -> str:
    """组装检索词，**类别词始终保留**

    keyword 只能作为额外限定，不能顶掉「酒店 / 住宿」这类类别词。
    否则像「北海 + 海景」会搜回「海景房二手房成交价」这类房产文章而非酒店。
    """
    keyword = (keyword or "").strip()
    return f"{city} {keyword} {category}".strip() if keyword else f"{city} {category}"


class BochaClient:
    """博查 AI 搜索客户端"""

    TOOL = "博查 AI 搜索"

    def __init__(self) -> None:
        self.key: Optional[str] = settings.BOCHA_API_KEY
        self.base_url: str = (settings.BOCHA_BASE_URL or "https://api.bochaai.com").rstrip("/")
        self.path: str = settings.BOCHA_SEARCH_PATH or "/v1/web-search"
        self.summary: bool = bool(settings.BOCHA_SUMMARY)
        self.count: int = settings.BOCHA_COUNT
        self.freshness: str = settings.BOCHA_FRESHNESS or "noLimit"
        self.hotel_freshness: str = settings.BOCHA_HOTEL_FRESHNESS or "oneYear"
        self.timeout: int = settings.BOCHA_TIMEOUT
        # 瞬时故障（超时 / 网络中断 / 5xx / 429）的重试次数
        self.transient_retry: int = getattr(settings, "BOCHA_RETRY_ATTEMPTS", 3)
        self._retry_base: float = getattr(settings, "API_RETRY_BASE_DELAY", 0.8)
        self._retry_cap: float = getattr(settings, "API_RETRY_MAX_DELAY", 8.0)
        self._retry_jitter: float = getattr(settings, "API_RETRY_JITTER", 0.25)

    def _require_key(self) -> str:
        return require_key(
            self.TOOL,
            self.key,
            "BOCHA_API_KEY",
            "请到 https://open.bochaai.com 申请博查 API Key 并填入 .env",
        )

    async def _sleep_before_retry(self, reason: str, attempt: int, total: int) -> None:
        """退避等待，并把「即将重试」推给前端"""
        delay = backoff_delay(attempt - 1, self._retry_base, self._retry_cap, self._retry_jitter)
        logger.warning(
            "⏳ 博查%s，%.1fs 后重试（第 %d/%d 次）", reason, delay, attempt, total
        )
        notify_retry(self.TOOL, attempt, total, delay, reason)
        await asyncio.sleep(delay)

    async def search(
        self,
        query: str,
        *,
        count: Optional[int] = None,
        freshness: Optional[str] = None,
        summary: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """执行一次联网检索（瞬时故障会退避重试）"""
        key = self._require_key()
        url = f"{self.base_url}{self.path}"

        payload: Dict[str, Any] = {
            "query": query,
            # 博查的 count 上限为 50，超出会被上游拒绝
            "count": max(1, min(int(count or self.count), _BOCHA_MAX_COUNT)),
            "summary": self.summary if summary is None else bool(summary),
            "freshness": _normalize_freshness(freshness or self.freshness),
        }

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        transient_left = self.transient_retry

        while True:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                reason = retry_reason(e)
                if transient_left > 0:
                    transient_left -= 1
                    await self._sleep_before_retry(
                        reason, self.transient_retry - transient_left, self.transient_retry
                    )
                    continue
                if isinstance(e, httpx.TimeoutException):
                    raise ToolCallError(
                        self.TOOL,
                        f"检索超时（{self.timeout}s），已重试 {self.transient_retry} 次仍失败",
                    )
                raise ToolCallError(
                    self.TOOL, f"网络错误，已重试 {self.transient_retry} 次仍失败：{e}"
                )

            # 5xx / 429 属瞬时故障；重试耗尽后再走下面的常规错误处理
            if response.status_code in RETRYABLE_STATUS_CODES and transient_left > 0:
                transient_left -= 1
                await self._sleep_before_retry(
                    describe_status_reason(response.status_code),
                    self.transient_retry - transient_left,
                    self.transient_retry,
                )
                continue

            raise_for_bocha_http(response)
            break
        try:
            data = response.json()
        except ValueError:
            raise ToolCallError(self.TOOL, f"返回内容不是 JSON：{response.text[:200]}")

        if not isinstance(data, dict):
            raise ToolCallError(self.TOOL, "返回了非预期的响应格式")

        # 博查错误通过 code / msg 返回（HTTP 仍可能是 200）
        code = data.get("code")
        if code is not None and str(code) not in ("200", "0"):
            raise ToolCallError(
                self.TOOL, f"上游报错 code={code}：{data.get('msg') or '未知错误'}"
            )

        web_pages = _unwrap_web_pages(data)
        raw_values = web_pages.get("value") or []
        results = self._normalize_results(raw_values)
        # 博查把检索词改写后的结果放在 queryContext.originalQuery
        query_context = (data.get("data") or {}).get("queryContext") if _has_data(data) else None
        original_query = (query_context or {}).get("originalQuery") if isinstance(query_context, dict) else None

        return {
            "query": original_query or query,
            "answer": _compose_summary(results),
            "results": results,
            "total_matches": web_pages.get("totalEstimatedMatches"),
        }

    # --------------------------------------------------- 景点 / 酒店 检索封装
    async def search_attractions(
        self, city: str, keyword: str = "", limit: int = 8
    ) -> Dict[str, Any]:
        """联网检索城市的必去景点与周边必玩地点"""
        query = _build_query(city, keyword, "必去景点 必玩 游玩攻略")
        return await self._search_places(
            city=city,
            query=query,
            limit=limit,
            freshness=self.freshness,
            not_found=(
                f"未检索到「{city} {keyword or '必去景点'}」相关的景点信息，"
                "请尝试其他城市或关键词"
            ),
        )

    async def search_hotels(
        self, city: str, keyword: str = "", limit: int = 8
    ) -> Dict[str, Any]:
        """联网检索城市的酒店 / 住宿信息"""
        query = _build_query(city, keyword, "酒店 住宿 推荐 参考价格")
        return await self._search_places(
            city=city,
            query=query,
            limit=limit,
            # 酒店价格与口碑时效性强，限定在较近的时间范围内
            freshness=self.hotel_freshness,
            not_found=(
                f"未检索到「{city} {keyword or '酒店住宿'}」相关的住宿信息，"
                "请尝试其他关键词"
            ),
        )

    async def _search_places(
        self,
        *,
        city: str,
        query: str,
        limit: int,
        not_found: str,
        freshness: Optional[str] = None,
    ) -> Dict[str, Any]:
        """景点/酒店共用的检索与整理逻辑"""
        data = await self.search(query=query, count=limit, freshness=freshness)

        sources: List[Dict[str, str]] = [
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "published_date": item.get("published_date") or "",
            }
            for item in data["results"]
            if item.get("url")
        ]

        if not data["answer"] and not data["results"]:
            raise ToolCallError(self.TOOL, not_found)

        return {
            "city": city,
            "query": data["query"],
            "answer": data["answer"],
            "results": data["results"],
            "sources": sources,
            "total_matches": data.get("total_matches"),
            "text": self._compose_text(query, data, sources),
        }

    @staticmethod
    def _normalize_results(results: List[Any]) -> List[Dict[str, Any]]:
        """把博查的 webPages.value[] 归一化成内部统一结构

        博查字段：name / url / snippet / summary / siteName / datePublished
        """
        normalized: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            # summary 是正文摘要（更详细），snippet 是简短摘要，优先用前者
            content = item.get("summary") or item.get("snippet") or ""
            normalized.append(
                {
                    "title": (item.get("name") or "").strip(),
                    "url": (item.get("url") or "").strip(),
                    "content": str(content).strip()[:_SNIPPET_LIMIT],
                    "snippet": (item.get("snippet") or "").strip(),
                    "site_name": (item.get("siteName") or "").strip(),
                    "published_date": (item.get("datePublished") or "").strip(),
                }
            )
        return normalized

    @staticmethod
    def _compose_text(query: str, data: Dict[str, Any], sources: List[Dict[str, str]]) -> str:
        """把检索结果整理成给大模型看的文本块"""
        lines: List[str] = [
            f"# 联网检索结果（博查 AI 搜索，检索日 {date.today().isoformat()}）",
            f"检索词：{query}",
            "",
        ]

        # 博查不提供 answer 字段，摘要由前几条来源节选拼接而成
        if data["answer"]:
            lines += ["## 摘要（节选自各来源）", data["answer"], ""]

        if data["results"]:
            lines.append("## 来源摘录")
            for index, item in enumerate(data["results"], 1):
                title = item.get("title") or "(无标题)"
                site = item.get("site_name") or ""
                published = item.get("published_date") or ""
                meta_parts = [p for p in (site, published) if p]
                meta = f"（{'，'.join(meta_parts)}）" if meta_parts else ""
                lines.append(f"{index}. {title}{meta}")
                if item.get("url"):
                    lines.append(f"   链接：{item['url']}")
                if item.get("content"):
                    lines.append(f"   内容：{item['content']}")
                lines.append("")

        if sources:
            lines.append("## 引用来源")
            lines.extend(f"- {s['title']} {s['url']}".rstrip() for s in sources)

        return "\n".join(lines).strip()


# --------------------------------------------------------------- 模块级工具函数
def _has_data(payload: Dict[str, Any]) -> bool:
    return isinstance(payload.get("data"), dict)


def _unwrap_web_pages(payload: Dict[str, Any]) -> Dict[str, Any]:
    """兼容两种响应形态：带 data 包装 与 直接返回

    博查官方 SDK 走 `data.webPages.value[]`，但也有接口/网关直接返回顶层对象，
    这里两种都接受，避免因包装层差异导致解析失败。
    """
    if _has_data(payload):
        web_pages = payload["data"].get("webPages")
    else:
        web_pages = payload.get("webPages")
    return web_pages if isinstance(web_pages, dict) else {}


def _compose_summary(results: List[Dict[str, Any]]) -> str:
    """从排名靠前的来源摘要拼接出「综合摘要」

    博查不提供 answer 字段，这里只做**节选拼接**，不做任何生成式改写，
    因此内容仍可溯源到具体来源。
    """
    parts: List[str] = []
    for item in results[:_SUMMARY_SOURCES]:
        text = (item.get("content") or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _normalize_freshness(value: str) -> str:
    """校验时间范围取值，非法值退回 noLimit（避免上游报错）"""
    value = (value or "").strip()
    if value in _BOCHA_FRESHNESS:
        return value
    # 允许自定义日期范围：YYYY-MM-DD 或 YYYY-MM-DD..YYYY-MM-DD
    if value and all(ch.isdigit() or ch in "-.~" for ch in value):
        return value
    if value:
        logger.warning("⚠ 非法的 freshness 取值「%s」，已退回 noLimit", value)
    return "noLimit"


def raise_for_bocha_http(response: httpx.Response) -> None:
    """把博查的 HTTP 错误转成可读且**不误导**的说明

    博查的错误细节在响应体里（message / msg / code），且 403 既可能是 Key 无权，
    也可能是**账户余额或套餐配额不足**。如果统一报成「鉴权失败，请检查 Key」，
    会把排查方向带偏，所以这里优先透传上游的原始说明。
    """
    if response.status_code == 200:
        return

    upstream = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            upstream = str(body.get("message") or body.get("msg") or "").strip()
    except ValueError:
        upstream = ""

    if response.status_code == 401:
        detail = "鉴权失败（HTTP 401）：API Key 无效或未生效"
    elif response.status_code == 403:
        detail = (
            "无权访问（HTTP 403）：可能是 API Key 无效，"
            "也可能是**账户余额或套餐配额不足**，请到博查控制台确认"
        )
    elif response.status_code == 429:
        detail = "请求过于频繁（HTTP 429），请稍后重试"
    else:
        detail = f"上游返回 HTTP {response.status_code}"

    if upstream:
        detail += f"。上游说明：{upstream}"

    raise ToolCallError("博查 AI 搜索", detail, response.status_code)


__all__ = ["BochaClient", "_build_query", "_normalize_freshness", "raise_for_bocha_http"]
