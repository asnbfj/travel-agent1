"""从 AI 生成的行程中推断行程字段

用途：用户点「保存到我的行程」时，先用这里的推断结果**预填确认弹窗**，
用户确认后才真正落库。

为什么需要这一步：`Trip` 的 `title / destination / start_date / end_date` 都是
必填，而出发日期无法从对话里可靠得知（用户可能只说「4 月份」「国庆」）。
与其静默写入一个猜的日期，不如推断出「最可能的值」交给用户确认。

本模块是纯函数、不依赖数据库与大模型，便于单测。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 正则

# Markdown 标题行
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
# 分日标记：Day 1 / 第 1 天 / D1（允许前面有 # 标题符或 - * 列表符）
_DAY_EN_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,6}|[-*+>])?\s*\**\s*(?:day|d)(?![a-z])\s*[-—]?\s*(\d{1,2})\b",
    re.IGNORECASE,
)
_DAY_CN_RE = re.compile(r"第\s*(\d{1,3})\s*天")
# 用户输入里的「N 天」
_DAYS_RE = re.compile(r"(\d{1,3})\s*(?:天|日)\s*(?:\d|晚)?")
# 用户输入里的「N 人」
_TRAVELERS_RE = re.compile(r"(\d{1,2})\s*(?:个?人|位)")
# 预算：优先「预算 2 万」这种带标签的写法，其次 ¥/￥，最后「3000 元」
_BUDGET_LABELED_RE = re.compile(r"预算[^\d¥￥]{0,8}[¥￥]?\s*(\d+(?:\.\d+)?)\s*(万|千|w|k)?", re.IGNORECASE)
_BUDGET_SYMBOL_RE = re.compile(r"[¥￥]\s*(\d+(?:\.\d+)?)\s*(万|千|w|k)?", re.IGNORECASE)
_BUDGET_YUAN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(万|千|w|k)?\s*(?:元|块钱|块|人民币)")
# 日期
_FULL_DATE_RE = re.compile(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})\s*[日号]?")
_MONTH_DAY_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
_MONTH_RE = re.compile(r"(\d{1,2})\s*月份?")
# 只有公历固定的假期才做映射（春节/端午/中秋是农历，无法按公历推算）
_HOLIDAYS: Dict[str, Tuple[int, int]] = {
    "元旦": (1, 1),
    "清明": (4, 4),
    "清明节": (4, 4),
    "五一": (5, 1),
    "劳动节": (5, 1),
    "国庆": (10, 1),
    "国庆节": (10, 1),
}

# 推断出的日期最多只信赖这个范围，超出的视为幻觉/误匹配而丢弃
_MAX_PAST_DAYS = 400
_MAX_FUTURE_DAYS = 800

# 目的地可从这些工具的 city 参数推断（它们都按城市查询）
_CITY_TOOLS = ("get_weather", "search_attractions", "search_hotels", "plan_route")

# 从标题里剥掉的装饰性字符（emoji、序号、符号）
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u2B00-\u2BFF\u2190-\u21FF]"
)
_LEADING_NOISE_RE = re.compile(r"^[\s\d]+[、.．)）:：\-—·]*\s*")
# 中文序号前缀，例如「二、3 天行程」里的「二、」
_CN_ORDINAL_RE = re.compile(r"^[一二三四五六七八九十百]+[、.．)）:：]?\s*")
_TITLE_CUT_RE = re.compile(r"(\d+\s*[天日]|行程|规划|攻略|之旅|旅游|自由行|路线|安排)")

# 明显不是目的地的章节名：宁可留空让用户填，也不要塞一个错的
_NOT_A_CITY = frozenset({
    "天气", "天气速览", "行程", "行程总览", "行程概览", "概览", "总览", "预算", "费用",
    "交通", "住宿", "酒店", "美食", "餐饮", "攻略", "注意事项", "贴士", "提示", "总结",
    "地图", "路线", "路线规划", "行程安排", "每日行程", "行前准备", "签证", "通讯",
})

# 出现在这些词附近的完整日期通常是「数据发布时间」而不是出发日期
_TIMESTAMP_CONTEXT = ("发布", "更新", "查询", "获取", "数据时间", "生成时间", "抓取")

# 默认值
DEFAULT_DAYS = 3
DEFAULT_TRAVELERS = 1
DEFAULT_BUDGET = 0


# ---------------------------------------------------------------- 工具

def _clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _to_int(value: str, multiplier: int = 1) -> Optional[int]:
    try:
        return int(round(float(value) * multiplier))
    except (TypeError, ValueError):
        return None


def _unit_multiplier(unit: Optional[str]) -> int:
    if not unit:
        return 1
    return {"万": 10000, "w": 10000, "千": 1000, "k": 1000}.get(unit.lower(), 1)


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:  # 例如 2 月 30 日
        return None


def _is_plausible(candidate: date, today: date) -> bool:
    """丢弃明显不合理的日期（把 2 月 30 日之类误匹配挡在前面之外再兜一层）"""
    delta = (candidate - today).days
    return -_MAX_PAST_DAYS <= delta <= _MAX_FUTURE_DAYS


def _next_occurrence(month: int, day: int, today: date) -> Optional[date]:
    """返回今年或明年的该月日（已过则取下一年），用于「4 月份」「国庆」这类说法"""
    candidate = _safe_date(today.year, month, day)
    if candidate is None:
        return None
    if candidate < today:
        candidate = _safe_date(today.year + 1, month, day)
    return candidate


# ---------------------------------------------------------------- 提取

def extract_destination(
    markdown: str = "",
    weather_info: Optional[Dict[str, Any]] = None,
    tool_calls: Optional[Sequence[Dict[str, Any]]] = None,
) -> str:
    """推断目的地

    优先级：天气接口返回的城市 > 工具调用的 city 参数 > 「X 天行程」式标题。
    前两者来自真实工具调用，几乎总是可信的。
    """
    city = _clean_text((weather_info or {}).get("city"))
    if city:
        return city

    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        if call.get("name") not in _CITY_TOOLS:
            continue
        args = call.get("args") or {}
        if not isinstance(args, dict):
            continue
        # 只认 city 参数：route 工具的 origin/destination 是景点而非行程所在城市
        value = _clean_text(args.get("city"))
        if value:
            return value

    # 退而求其次：在标题里找「北海 3 天行程」这种模式
    for raw in _HEADING_RE.findall(markdown or ""):
        text = _EMOJI_RE.sub("", raw).strip()
        if not re.search(r"\d+\s*[天日]", text):
            continue
        city_part = _TITLE_CUT_RE.split(text)[0]
        city_part = _LEADING_NOISE_RE.sub("", city_part)
        city_part = _CN_ORDINAL_RE.sub("", city_part)
        # 在括号 / 斜杠 / 破折号处截断，避免留下「注意事项（含」这类残片
        city_part = re.split(r"[（(【\[/·—|]", city_part)[0]
        city_part = city_part.strip(" ·-—,，。:：、")
        if not 2 <= len(city_part) <= 20:
            continue
        # 章节名（天气/预算/注意事项…）不是目的地，子串命中也要排除
        if city_part in _NOT_A_CITY or any(word in city_part for word in _NOT_A_CITY):
            continue
        return city_part
    return ""


def extract_days_count(
    markdown: str = "",
    user_message: Optional[str] = None,
    weather_info: Optional[Dict[str, Any]] = None,
) -> int:
    """推断行程天数

    优先级：正文的 Day N 编号（最贴近实际规划）> 用户原话「N 天」> 天气预报天数。
    """
    text = markdown or ""
    numbers: List[int] = []
    numbers += [int(n) for n in _DAY_EN_RE.findall(text)]
    numbers += [int(n) for n in _DAY_CN_RE.findall(text)]
    if numbers:
        # 用最大编号而不是出现次数，避免「Day 1」被正文重复提及时数错
        return max(1, min(max(numbers), 60))

    match = _DAYS_RE.search(user_message or "")
    if match:
        return max(1, min(int(match.group(1)), 60))

    forecasts = (weather_info or {}).get("forecasts") or []
    if forecasts:
        return max(1, min(len(forecasts), 60))

    return DEFAULT_DAYS


def extract_travelers(user_message: Optional[str] = None) -> int:
    """从用户原话里推断人数，例如「5 天 3 人」→ 3"""
    match = _TRAVELERS_RE.search(user_message or "")
    if match:
        return max(1, min(int(match.group(1)), 50))
    return DEFAULT_TRAVELERS


def extract_budget(user_message: Optional[str] = None) -> int:
    """从用户原话里推断预算，支持「预算 2 万」「¥3000」「3000 元」"""
    text = user_message or ""
    for pattern in (_BUDGET_LABELED_RE, _BUDGET_SYMBOL_RE, _BUDGET_YUAN_RE):
        match = pattern.search(text)
        if not match:
            continue
        amount = _to_int(match.group(1), _unit_multiplier(match.group(2)))
        if amount and amount > 0:
            return min(amount, 100_000_000)
    return DEFAULT_BUDGET


def _full_dates_in(text: str) -> Iterable[Tuple[date, int]]:
    """按出现顺序返回文本里的完整日期及其起始位置"""
    for match in _FULL_DATE_RE.finditer(text or ""):
        candidate = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if candidate:
            yield candidate, match.start()


def _is_timestamp_context(text: str, position: int, window: int = 15) -> bool:
    """判断该日期是否紧跟在「发布 / 更新 / 查询」等词之后（那是数据时间，不是出发日期）"""
    prefix = (text or "")[max(0, position - window):position]
    return any(word in prefix for word in _TIMESTAMP_CONTEXT)


def extract_start_date(
    markdown: str = "",
    user_message: Optional[str] = None,
    today: Optional[date] = None,
) -> Optional[date]:
    """推断出发日期；实在推断不出时返回 None（由调用方决定兜底值）

    用户原话优先于正文：正文里常出现「天气数据发布于 X」，那不是出发日期。
    """
    today = today or date.today()
    md = markdown or ""
    msg = user_message or ""

    # 1) 用户原话里的完整日期（2026-10-01 / 2026 年 10 月 1 日）最可信
    for candidate, _ in _full_dates_in(msg):
        if _is_plausible(candidate, today):
            return candidate

    # 2) 正文里的完整日期，但跳过「发布日期」这类时间戳附近的日期
    for candidate, position in _full_dates_in(md):
        if _is_timestamp_context(md, position):
            continue
        if _is_plausible(candidate, today):
            return candidate

    # 3) 原话里的「10 月 1 日」
    match = _MONTH_DAY_RE.search(msg)
    if match:
        candidate = _next_occurrence(int(match.group(1)), int(match.group(2)), today)
        if candidate:
            return candidate

    # 4) 原话里的假期名（只处理公历固定的）
    for name, (month, day) in _HOLIDAYS.items():
        if name in msg:
            candidate = _next_occurrence(month, day, today)
            if candidate:
                return candidate

    # 5) 原话里只有月份，例如「4 月份」
    match = _MONTH_RE.search(msg)
    if match:
        month = int(match.group(1))
        if 1 <= month <= 12:
            candidate = _next_occurrence(month, 1, today)
            if candidate:
                return candidate

    return None


def extract_title(markdown: str = "", destination: str = "", days: int = DEFAULT_DAYS) -> str:
    """推断行程标题：优先「目的地 + 天数」，否则退回头一个像样的标题行"""
    if destination:
        return f"{destination} {days} 天行程"

    headings = [
        _EMOJI_RE.sub("", raw).strip(" ·-—#") for raw in _HEADING_RE.findall(markdown or "")
    ]
    def looks_like_title(text: str) -> bool:
        """必须含「N 天 / N 日」或「行程 / 之旅」，光有「天」字会把「天气速览」误判成标题"""
        return bool(re.search(r"\d+\s*[天日]", text)) or any(
            kw in text for kw in ("行程", "之旅", "自由行", "旅游")
        )

    for text in headings:
        if not looks_like_title(text):
            continue
        if 2 <= len(text) <= 40 and text not in _NOT_A_CITY:
            return _CN_ORDINAL_RE.sub("", text).strip(" ·-—,:：、") or text
    for text in headings:
        if 2 <= len(text) <= 40 and text not in _NOT_A_CITY:
            return text
    return f"{days} 天旅行行程"


def infer_trip_fields(
    *,
    content: str,
    weather_info: Optional[Dict[str, Any]] = None,
    tool_calls: Optional[Sequence[Dict[str, Any]]] = None,
    user_message: Optional[str] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """推断一份行程的落库字段（用于「保存到我的行程」弹窗预填）

    Returns:
        含 title / destination / start_date / end_date / budget / travelers / days_count
    """
    today = today or date.today()
    destination = extract_destination(content, weather_info, tool_calls)
    days = extract_days_count(content, user_message, weather_info)
    start = extract_start_date(content, user_message, today) or today
    end = start + timedelta(days=days - 1)

    return {
        "title": extract_title(content, destination, days),
        "destination": destination,
        "start_date": start,
        "end_date": end,
        "budget": extract_budget(user_message),
        "travelers": extract_travelers(user_message),
        "days_count": days,
    }


__all__ = [
    "infer_trip_fields",
    "extract_destination",
    "extract_days_count",
    "extract_travelers",
    "extract_budget",
    "extract_start_date",
    "extract_title",
]
