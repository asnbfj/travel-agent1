"""行程字段推断测试（`app/services/plan_extract.py`）

该模块负责「保存到我的行程」弹窗的预填值，属于纯函数，测试重点在：
- 能从真实形态的行程文本里正确取值
- **取不到时宁可留空/退回默认值，也不要猜一个错的**（错误目的地/日期比空值更有害）
"""
from datetime import date

import pytest

from app.services.plan_extract import (
    extract_budget,
    extract_days_count,
    extract_destination,
    extract_start_date,
    extract_title,
    extract_travelers,
    infer_trip_fields,
)

TODAY = date(2026, 9, 30)

WEATHER = {
    "city": "北海",
    "source": "高德地图",
    "report_time": "2026-09-30 09:35:09",
    "tips": "气温较高，注意防暑防晒。",
    "forecasts": [
        {"date": "2026-09-30", "weekday": "周三", "weather": "多云"},
        {"date": "2026-10-01", "weekday": "周四", "weather": "多云"},
        {"date": "2026-10-02", "weekday": "周五", "weather": "多云"},
    ],
}

PLAN = """## 🌤 一、天气速览

北海未来三天多云，**适合下海**。数据发布于 2026-09-30 09:35:09。

## 🗺 二、3 天行程

### Day 1｜银滩看海 + 侨港吃海鲜

- **上午**：北海银滩，建议 3 小时。

### Day 2｜涠洲岛一日

- 鳄鱼山火山口地貌 → 滴水丹屏日落。

### Day 3｜老城与返程

- 北海老街，购买海味手信。
"""


# --------------------------------------------------------------- 目的地

def test_destination_prefers_weather_city():
    """天气接口返回的城市是最可信的来源"""
    assert extract_destination(PLAN, WEATHER, []) == "北海"


def test_destination_falls_back_to_tool_call_args():
    calls = [{"name": "search_attractions", "args": {"city": "大理", "keyword": "必去"}}]
    assert extract_destination("## 行程", None, calls) == "大理"


def test_destination_ignores_route_tool_endpoints():
    """路线工具的 origin/destination 是景点，不是行程所在城市，不应拿来当目的地"""
    calls = [{"name": "plan_route", "args": {"origin": "丽江古城", "destination": "玉龙雪山"}}]
    assert extract_destination("正文没有城市标题", None, calls) == ""


def test_destination_reads_city_from_route_tool_when_present():
    calls = [{"name": "plan_route", "args": {"origin": "银滩", "destination": "涠洲岛", "city": "北海"}}]
    assert extract_destination("", None, calls) == "北海"


def test_destination_ignores_unrelated_tool_calls():
    calls = [{"name": "get_weather", "args": {"days": 3}}]
    assert extract_destination("正文没有城市标题", None, calls) == ""


def test_destination_extracted_from_xxx_days_heading():
    """没有工具数据时，从「北海 3 天行程」这类标题里取城市"""
    assert extract_destination("## 北海 3 天「看海」行程\n\n正文", None, None) == "北海"
    assert extract_destination("## 🏖 东京 · 5天赏樱自由行", None, None) == "东京"


@pytest.mark.parametrize("heading", [
    "## 🌤 一、天气速览",
    "## 二、3 天行程",
    "## 预算与费用",
    "## 注意事项（含 3 天天气）",
])
def test_destination_not_guessed_from_section_headings(heading):
    """章节名不是目的地：宁可留空，也不要猜一个错的"""
    assert extract_destination(f"{heading}\n\n正文内容", None, None) == ""


def test_destination_empty_when_nothing_usable():
    assert extract_destination("", None, None) == ""
    assert extract_destination(None, None, None) == ""


# --------------------------------------------------------------- 天数

def test_days_count_from_day_headings():
    assert extract_days_count(PLAN, None, None) == 3


def test_days_count_uses_max_not_occurrences():
    """「Day 1」在正文里被反复提及也不能把天数算多"""
    md = "### Day 1｜出发\n\n- Day 1 晚上入住\n- Day 1 小结\n\n### Day 2｜返程\n"
    assert extract_days_count(md, None, None) == 2


def test_days_count_supports_chinese_and_bullet_forms():
    assert extract_days_count("### 第 4 天｜返程", None, None) == 4
    assert extract_days_count("- **Day 6**：自由活动", None, None) == 6
    assert extract_days_count("D2｜环岛", None, None) == 2


def test_days_count_is_not_fooled_by_english_words():
    """不能把 documents / data 之类的词当成 Day"""
    assert extract_days_count("documents 5 files", None, WEATHER) == 3  # 退回天气预报天数


def test_days_count_falls_back_to_user_message():
    assert extract_days_count("## 行程\n\n没有分日", "想去北海，5天2人", None) == 5


def test_days_count_falls_back_to_forecast_length():
    assert extract_days_count("", None, WEATHER) == 3


def test_days_count_default_when_nothing_available():
    assert extract_days_count("", None, None) == 3


# --------------------------------------------------------------- 人数

@pytest.mark.parametrize("message,expected", [
    ("我想去北海，3天，2人，预算3000", 2),
    ("5天3人", 3),
    ("带父母一起去，共 4 位", 4),
    ("和朋友 12 人去东京", 12),
])
def test_travelers_extracted(message, expected):
    assert extract_travelers(message) == expected


@pytest.mark.parametrize("message", ["我想去北海", "", None, "预算 5000 元"])
def test_travelers_default_when_absent(message):
    assert extract_travelers(message) == 1


# --------------------------------------------------------------- 预算

@pytest.mark.parametrize("message,expected", [
    ("预算3000", 3000),
    ("预算 3000 元", 3000),
    ("预算2万", 20000),
    ("预算 1.5 万", 15000),
    ("预算5千", 5000),
    ("总预算￥8000", 8000),
    ("人均 500，一共 3000 元", 3000),
])
def test_budget_extracted(message, expected):
    assert extract_budget(message) == expected


@pytest.mark.parametrize("message", ["", None, "我想去北海，3天，2人", "预算充足"])
def test_budget_zero_when_absent(message):
    """推断不出就返回 0（表示未设置），不要拿天数/人数当预算"""
    assert extract_budget(message) == 0


def test_budget_not_confused_by_days_or_travelers():
    """「5天3人」里没有任何预算信息"""
    assert extract_budget("我想去北海，5天3人") == 0


# --------------------------------------------------------------- 出发日期

def test_start_date_from_user_message_full_date():
    assert extract_start_date("", "2026-10-01 出发去北海", TODAY) == date(2026, 10, 1)
    assert extract_start_date("", "2026年10月1日出发", TODAY) == date(2026, 10, 1)


def test_start_date_from_user_message_month_day():
    assert extract_start_date("", "10月1日去北海", TODAY) == date(2026, 10, 1)


def test_start_date_rolls_to_next_year_when_past():
    """用户说「1 月 20 日」而今天已是 9 月，应理解为明年"""
    assert extract_start_date("", "1月20日去哈尔滨", TODAY) == date(2027, 1, 20)


@pytest.mark.parametrize("message,expected", [
    ("国庆去北海", date(2026, 10, 1)),
    ("元旦去哈尔滨", date(2027, 1, 1)),
    ("五一去三亚", date(2027, 5, 1)),
    ("清明节去婺源", date(2027, 4, 4)),
])
def test_start_date_from_public_holidays(message, expected):
    """只认公历固定的假期；春节/端午/中秋是农历，不猜"""
    assert extract_start_date("", message, TODAY) == expected


def test_start_date_from_month_only():
    assert extract_start_date("", "4月份去日本", TODAY) == date(2027, 4, 1)


def test_start_date_ignores_weather_report_timestamp():
    """正文里的「数据发布于 2026-09-30」不是出发日期"""
    md = "北海未来三天多云。数据发布于 2026-09-30 09:35:09。\n\n**出发日期：2026-10-05**"
    assert extract_start_date(md, None, TODAY) == date(2026, 10, 5)


def test_start_date_ignores_all_timestamps_when_no_real_date():
    md = "天气数据更新时间 2026-09-30，查询时间 2026-09-30。"
    assert extract_start_date(md, None, TODAY) is None


def test_start_date_rejects_absurd_dates():
    """明显不合理的年份（误匹配）应被丢弃"""
    assert extract_start_date("出发 1900-01-01", None, TODAY) is None
    assert extract_start_date("出发 2200-01-01", None, TODAY) is None


def test_start_date_handles_invalid_month_day():
    """2 月 30 日这种不存在的日期不能抛异常"""
    assert extract_start_date("出发 2026-02-30", None, TODAY) is None


def test_start_date_returns_none_when_unknown():
    assert extract_start_date(PLAN, None, TODAY) is None
    assert extract_start_date("", None, TODAY) is None


# --------------------------------------------------------------- 标题

def test_title_prefers_destination_and_days():
    assert extract_title(PLAN, "北海", 3) == "北海 3 天行程"


def test_title_from_heading_when_no_destination():
    title = extract_title("## 🌤 一、天气速览\n\n## 东京 5 天赏樱之旅\n\n正文", "", 5)
    assert "东京" in title and "天气速览" not in title


# --------------------------------------------------------------- 综合

def test_infer_trip_fields_end_to_end():
    fields = infer_trip_fields(
        content=PLAN,
        weather_info=WEATHER,
        tool_calls=[{"name": "get_weather", "args": {"city": "北海"}}],
        user_message="我想去北海，3天，2人，预算3000，10月1日出发",
        today=TODAY,
    )
    assert fields == {
        "title": "北海 3 天行程",
        "destination": "北海",
        "start_date": date(2026, 10, 1),
        "end_date": date(2026, 10, 3),
        "budget": 3000,
        "travelers": 2,
        "days_count": 3,
    }


def test_infer_trip_fields_never_returns_empty_required_fields():
    """Trip 的 title / destination / 日期都是必填，推断结果必须可用"""
    fields = infer_trip_fields(content="随便一段没有结构的文字", today=TODAY)
    assert fields["title"]
    assert fields["destination"] == ""          # 宁可留空交给用户填
    assert fields["start_date"] == TODAY        # 兜底为今天
    assert fields["end_date"] >= fields["start_date"]
    assert fields["days_count"] >= 1


def test_infer_end_date_matches_days_count():
    fields = infer_trip_fields(
        content="### Day 1\n### Day 2\n### Day 3\n### Day 4\n### Day 5",
        user_message="2026-10-01 出发",
        today=TODAY,
    )
    assert fields["days_count"] == 5
    assert fields["end_date"] == date(2026, 10, 5)
