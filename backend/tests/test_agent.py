"""工具层单元测试（数据源拆分后的新契约）

数据源分工：
    天气 + 路线规划  -> 高德地图 API
    景点 / 必玩 / 酒店 -> 博查 AI 搜索（联网检索）

全部为**离线测试**：不发起任何真实网络请求，也不需要 API Key。
"""
import asyncio
import json
import time

import pytest

from app.agent.tools import collector as collector_module
from app.agent.tools.collector import start_collector
from app.agent.tools.errors import ToolConfigError, ToolCallError
from app.agent.tools import amap_client as amap_module
from app.agent.tools import bocha_client as bocha_module
from app.agent.tools.amap_client import (
    AmapClient,
    _AmapRateLimiter,
    _is_qps_error,
    _validate_city_match,
)
from app.agent.tools.bocha_client import BochaClient, _normalize_freshness
from app.agent.tools.booking_tools import search_hotels
from app.agent.tools.spot_tools import search_attractions
from app.agent.tools.weather_tools import get_weather, _build_tips, _to_icon


# --------------------------------------------------------------------- 测试替身
class _FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload, ensure_ascii=False) if payload else "")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _FakeAsyncClient:
    """替代 httpx.AsyncClient：记录请求，并按顺序返回预置响应"""

    calls: list = []
    responses: list = []
    _cursor: int = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        type(self).calls.append({"url": url, "json": json, "headers": headers})
        return self._next()

    async def get(self, url, params=None, headers=None):
        type(self).calls.append({"url": url, "params": params, "headers": headers})
        return self._next()

    @classmethod
    def _next(cls):
        response = cls.responses[min(cls._cursor, len(cls.responses) - 1)]
        cls._cursor += 1
        return response

    @classmethod
    def last_call(cls):
        return cls.calls[-1]

    @classmethod
    def reset(cls, responses):
        cls.calls = []
        cls.responses = list(responses)
        cls._cursor = 0


@pytest.fixture(autouse=True)
def _reset_collector():
    """每个用例前后都清理 contextvar 收集器，避免用例间串扰"""
    collector_module._collector.set(None)
    yield
    collector_module._collector.set(None)


async def _no_sleep(_seconds):
    """替换 asyncio.sleep，避免测试里真的等待退避时间"""
    return None


@pytest.fixture(autouse=True)
def _reset_fake_http():
    _FakeAsyncClient.reset([])
    yield
    _FakeAsyncClient.reset([])


# ======================================================== 高德：天气（结构化）
_AMAP_GEO_OK = {
    "status": "1",
    "infocode": "10000",
    "geocodes": [
        {
            "formatted_address": "广西壮族自治区北海市",
            "province": "广西壮族自治区",
            "city": "北海市",
            "adcode": "450500",
            "district": "",
            "location": "109.119254,21.473343",
            "level": "市",
        }
    ],
}

_AMAP_WEATHER_OK = {
    "status": "1",
    "infocode": "10000",
    "count": "1",
    "forecasts": [
        {
            "city": "北海市",
            "province": "广西壮族自治区",
            "adcode": "450500",
            "reporttime": "2026-09-29 11:00:00",
            "casts": [
                {
                    "date": "2026-09-29",
                    "week": "2",
                    "dayweather": "晴",
                    "nightweather": "晴",
                    "daytemp": "30",
                    "nighttemp": "24",
                    "daywind": "东",
                    "daypower": "1-3",
                },
                {
                    "date": "2026-09-30",
                    "week": "3",
                    "dayweather": "多云",
                    "nightweather": "阴",
                    "daytemp": "29",
                    "nighttemp": "23",
                    "daywind": "东南",
                    "daypower": "3-4",
                },
            ],
        }
    ],
}


@pytest.mark.asyncio
async def test_amap_weather_uses_adcode_and_structured_cast(monkeypatch):
    """天气走高德：先地理编码换 adcode，再取逐日预报"""
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_AMAP_GEO_OK), _FakeResponse(payload=_AMAP_WEATHER_OK)])

    result = await AmapClient().get_forecast("北海", days=4)

    assert _FakeAsyncClient.calls[0]["url"].endswith("/geocode/geo")
    weather_call = _FakeAsyncClient.calls[1]
    assert weather_call["url"].endswith("/weather/weatherInfo")
    # 高德天气接口要求 adcode，而不是城市名
    assert weather_call["params"]["city"] == "450500"
    assert weather_call["params"]["extensions"] == "all"
    assert weather_call["params"]["key"] == "amap-test-key"

    assert result["kind"] == "forecast"
    assert result["report_time"] == "2026-09-29 11:00:00"
    first = result["casts"][0]
    assert first["weekday"] == "周二"
    assert (first["temp_low"], first["temp_high"]) == (24.0, 30.0)
    assert first["weather"] == "晴"
    # 白天/夜间不同 -> 组合成「X转Y」
    assert result["casts"][1]["weather"] == "多云转阴"
    assert result["casts"][1]["wind"] == "东南风3-4级"


@pytest.mark.asyncio
async def test_amap_weather_falls_back_to_live_when_no_cast(monkeypatch):
    """预报为空时退化为实况天气"""
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(payload=_AMAP_GEO_OK),
            _FakeResponse(payload={"status": "1", "infocode": "10000", "forecasts": []}),
            _FakeResponse(
                payload={
                    "status": "1",
                    "infocode": "10000",
                    "lives": [
                        {
                            "province": "广西壮族自治区",
                            "city": "北海市",
                            "adcode": "450500",
                            "weather": "晴",
                            "temperature": "31",
                            "winddirection": "东",
                            "windpower": "≤3",
                            "humidity": "60",
                            "reporttime": "2026-09-29 11:00:00",
                        }
                    ],
                }
            ),
        ]
    )

    result = await AmapClient().get_forecast("北海")
    assert result["kind"] == "live"
    assert result["live"]["weather"] == "晴"
    assert result["live"]["temperature"] == 31.0


# ---------------------------------------------------- 高德限速 / QPS 重试
@pytest.mark.asyncio
async def test_amap_rate_limiter_serializes_concurrent_requests():
    """并发请求必须被限速器串行摊平，否则会触发 10021"""
    limiter = _AmapRateLimiter(0.05)
    started = time.monotonic()
    await asyncio.gather(*[limiter.acquire() for _ in range(8)])
    elapsed = time.monotonic() - started
    # 8 次 acquire，最小间隔 0.05s -> 至少 7*0.05 = 0.35s
    assert elapsed >= 0.33


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"status": "0", "infocode": "10021"}, True),   # CUQPS 超限
        ({"status": "0", "infocode": "10019"}, True),
        ({"status": "0", "infocode": "10001"}, False),  # Key 无效，重试无意义
        ({"status": "1", "infocode": "10000"}, False),  # 成功
        ("not-a-dict", False),
    ],
)
def test_is_qps_error(payload, expected):
    assert _is_qps_error(payload) is expected


@pytest.mark.asyncio
async def test_amap_retries_on_qps_error_then_succeeds(monkeypatch):
    """命中 10021 应退避重试，而不是直接把错误抛给用户"""
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(amap_module.asyncio, "sleep", _no_sleep)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(payload={"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT", "infocode": "10021"}),
            _FakeResponse(payload=_AMAP_WEATHER_OK),
        ]
    )

    result = await AmapClient()._get("/weather/weatherInfo", {"city": "450500"})

    assert result["status"] == "1"
    assert len(_FakeAsyncClient.calls) == 2


@pytest.mark.asyncio
async def test_amap_raises_after_qps_retries_exhausted(monkeypatch):
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.settings, "AMAP_QPS_RETRY", 1)
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(amap_module.asyncio, "sleep", _no_sleep)
    _FakeClient = _FakeAsyncClient
    _FakeClient.reset(
        [
            _FakeResponse(payload={"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT", "infocode": "10021"}),
            _FakeResponse(payload={"status": "0", "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT", "infocode": "10021"}),
        ]
    )

    with pytest.raises(ToolCallError) as exc:
        await AmapClient()._get("/weather/weatherInfo", {"city": "450500"})
    assert "10021" in str(exc.value) or "QPS" in str(exc.value)
    # 1 次重试 = 共 2 次请求
    assert len(_FakeClient.calls) == 2


def test_amap_key_invalid_is_not_retried(monkeypatch):
    """Key 无效这类错误不该被当成 QPS 限流去重试"""
    assert _is_qps_error({"status": "0", "infocode": "10001"}) is False
    assert _is_qps_error({"status": "0", "infocode": "10009"}) is False


@pytest.mark.asyncio
async def test_amap_weather_without_key_raises_config_error(monkeypatch):
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", None)
    with pytest.raises(ToolConfigError) as exc:
        await AmapClient().get_forecast("北海")
    assert "AMAP_API_KEY" in str(exc.value)


# ----------------------------- 城市匹配校验（防止模糊匹配返回错误地方的天气）
_BOGUS_GEO = {
    "status": "1",
    "infocode": "10000",
    "geocodes": [
        {
            "formatted_address": "内蒙古自治区锡林郭勒盟正镶白旗星耀镇",
            "province": "内蒙古自治区",
            "city": "锡林郭勒盟",
            "adcode": "152529",
            "district": "正镶白旗",
            "location": "115.0,42.3",
            "level": "乡镇",
        }
    ],
}

# 实测高德会把「东京」模糊匹配到广西一个叫「东京」的村庄
_TOKYO_GEO = {
    "status": "1",
    "infocode": "10000",
    "geocodes": [
        {
            "formatted_address": "广西壮族自治区贵港市平南县东京",
            "province": "广西壮族自治区",
            "city": "贵港市",
            "adcode": "450821",
            "district": "平南县",
            "location": "110.3,23.5",
            "level": "村庄",
        }
    ],
}


@pytest.mark.asyncio
async def test_weather_rejects_non_city_level_match(monkeypatch):
    """被解析成乡镇/村庄时必须报错，绝不能返回另一个地方的天气"""
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_BOGUS_GEO)])

    with pytest.raises(ToolCallError) as exc:
        await AmapClient().get_forecast("不存在的地名XYZ")

    message = str(exc.value)
    assert "乡镇" in message
    # 必须把高德实际解析到的地方透出来，便于用户判断
    assert "锡林郭勒盟" in message
    # 未通过校验就不应再请求天气接口
    assert len(_FakeAsyncClient.calls) == 1


@pytest.mark.asyncio
async def test_weather_rejects_foreign_city_matched_to_village(monkeypatch):
    """'东京' 会被高德匹配成广西的村庄，必须拒绝而不是返回该村天气"""
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_TOKYO_GEO)])

    with pytest.raises(ToolCallError) as exc:
        await AmapClient().get_forecast("东京")
    assert "村庄" in str(exc.value)


@pytest.mark.parametrize(
    "requested,address,city,level",
    [
        ("涠洲岛", "广西壮族自治区北海市海城区涠洲岛", "北海市", "住宅区"),
        ("北海银滩", "广西壮族自治区北海市银海区银滩", "北海市", "风景名胜"),
    ],
)
def test_weather_suggests_parent_city_for_poi(requested, address, city, level):
    """解析到城市内的景点时，应提示改用上级城市查询，而不是只说「请提供更明确的城市名」"""
    with pytest.raises(ToolCallError) as exc:
        _validate_city_match(requested, {"address": address, "city": city, "level": level})

    message = str(exc.value)
    assert city in message          # 必须给出可用的替代城市名
    assert level in message


def test_weather_village_level_does_not_suggest_misleading_parent():
    """'东京' 匹配到的村庄其上级城市是无关的，不能给出误导性建议"""
    with pytest.raises(ToolCallError) as exc:
        _validate_city_match(
            "东京",
            {"address": "广西壮族自治区贵港市平南县东京", "city": "贵港市", "level": "村庄"},
        )

    message = str(exc.value)
    assert "境外城市" in message
    # 村庄级别的上级城市不可信，不应提示「请改用贵港市」
    assert "改用城市名" not in message


@pytest.mark.asyncio
async def test_weather_rejects_name_not_in_resolved_address(monkeypatch):
    """级别正常但名称对不上（模糊命中别的城市）也要拒绝"""
    mismatch = {
        "status": "1",
        "infocode": "10000",
        "geocodes": [
            {
                "formatted_address": "浙江省杭州市",
                "province": "浙江省",
                "city": "杭州市",
                "adcode": "330100",
                "location": "120.1,30.2",
                "level": "市",
            }
        ],
    }
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=mismatch)])

    with pytest.raises(ToolCallError) as exc:
        await AmapClient().get_forecast("北嘿")
    assert "准确匹配" in str(exc.value)


@pytest.mark.parametrize(
    "requested,address,level",
    [
        ("北海", "广西壮族自治区北海市", "市"),
        ("杭州", "浙江省杭州市", "市"),
        ("上海", "上海市", "省"),      # 直辖市在 高德 里 level 为「省」
        ("朝阳区", "北京市朝阳区", "区县"),   # 高德对区级返回的 level 是「区县」
    ],
)
def test_weather_accepts_legit_city_matches(requested, address, level):
    _validate_city_match(requested, {"address": address, "level": level})


def test_plan_route_is_not_subject_to_city_level_check():
    """路径规划的地点是景点/门牌号，级别为「兴趣点」也属正常，不能被拦"""
    # _validate_city_match 只用于天气；这里确认它不会被用于 plan_route 的解析路径
    from app.agent.tools.amap_client import _validate_city_match as guard
    with pytest.raises(ToolCallError):
        guard("北海银滩", {"address": "北海银滩", "level": "兴趣点"})
    # 说明该函数确实严格；因此它只挂在 get_forecast 上，不挂在 resolve_location 上
    import inspect
    source = inspect.getsource(AmapClient.plan_route)
    assert "_validate_city_match" not in source


@pytest.mark.asyncio
async def test_get_weather_collects_structured_card(monkeypatch):
    """get_weather 应把高德结构化预报交给前端卡片（无需大模型二次规整）"""
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_AMAP_GEO_OK), _FakeResponse(payload=_AMAP_WEATHER_OK)])

    start_collector()
    payload = json.loads(await get_weather.ainvoke({"city": "北海", "days": 2}))

    weather_info = collector_module.get_collector().get("weather_info")
    assert weather_info["city"] == "北海"
    assert weather_info["source"] == "高德地图"
    assert weather_info["report_time"] == "2026-09-29 11:00:00"

    day = weather_info["forecasts"][0]
    assert (day["date"], day["weekday"], day["icon"]) == ("2026-09-29", "周二", "☀")
    assert (day["temp_low"], day["temp_high"]) == (24, 30)
    assert payload["forecasts"][0]["date"] == "2026-09-29"
    assert "北海 天气预报" in payload["text"]


@pytest.mark.asyncio
async def test_get_weather_live_fallback_still_renders_card(monkeypatch):
    """只有实况天气时也要给出一天卡片，并说明无逐日预报"""
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(payload=_AMAP_GEO_OK),
            _FakeResponse(payload={"status": "1", "infocode": "10000", "forecasts": []}),
            _FakeResponse(
                payload={
                    "status": "1",
                    "infocode": "10000",
                    "lives": [{"city": "北海市", "adcode": "450500", "weather": "小雨", "temperature": "26"}],
                }
            ),
        ]
    )

    start_collector()
    payload = json.loads(await get_weather.ainvoke({"city": "北海"}))

    weather_info = collector_module.get_collector().get("weather_info")
    assert weather_info["forecasts"][0]["weather"] == "小雨"
    assert weather_info["forecasts"][0]["icon"] == "🌧"
    assert payload["forecasts"] == []
    assert "暂未返回逐日预报" in payload["text"]


@pytest.mark.parametrize(
    "weather,icon",
    [("晴", "☀"), ("多云", "⛅"), ("阴", "☁"), ("小雨", "🌧"), ("雷阵雨", "⛈"), ("雪", "❄"), ("未知现象", "🌤")],
)
def test_to_icon(weather, icon):
    assert _to_icon(weather) == icon


def test_build_tips_mentions_rain_and_heat():
    tips = _build_tips(
        [
            {"weather": "小雨", "temp_high": 33, "temp_low": 27},
            {"weather": "晴", "temp_high": 34, "temp_low": 28},
        ]
    )
    assert "雨具" in tips
    assert "防暑" in tips


def test_build_tips_default_when_nothing_notable():
    assert _build_tips([{"weather": "多云", "temp_high": 22, "temp_low": 18}]) == "天气总体良好，适合出行。"


# ============================================ 博查 AI 搜索：景点 / 酒店（联网检索）
def _bocha_payload(query: str, value: list, total: int = 1234) -> dict:
    """构造博查 /v1/web-search 的真实响应结构（含 data 包装）"""
    return {
        "code": 200,
        "log_id": "test-log-id",
        "msg": None,
        "data": {
            "_type": "SearchResponse",
            "queryContext": {"originalQuery": query},
            "webPages": {
                "webSearchUrl": "https://bochaai.com/search?q=test",
                "totalEstimatedMatches": total,
                "value": value,
            },
        },
    }


def _bocha_page(name: str, url: str, summary: str = "", snippet: str = "", **extra) -> dict:
    page = {
        "id": f"https://api.bochaai.com/v1/#WebPages.0.{name}",
        "name": name,
        "url": url,
        "siteName": "示例站点",
        "snippet": snippet or summary[:40],
        "summary": summary,
        "datePublished": "2026-09-01T00:00:00+08:00",
    }
    page.update(extra)
    return page


@pytest.mark.asyncio
async def test_bocha_requires_key(monkeypatch):
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", None)
    with pytest.raises(ToolConfigError) as exc:
        await BochaClient().search_attractions("北海")
    assert "BOCHA_API_KEY" in str(exc.value)


@pytest.mark.asyncio
async def test_bocha_attractions_request_and_text(monkeypatch):
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.settings, "BOCHA_SUMMARY", True)
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(
                payload=_bocha_payload(
                    "北海 必去景点 必玩 游玩攻略",
                    [
                        _bocha_page(
                            "北海必玩景点",
                            "https://example.com/beihai",
                            summary="银滩适合看日落，涠洲岛需要坐船。",
                        )
                    ],
                )
            )
        ]
    )

    result = await BochaClient().search_attractions("北海", limit=8)

    captured = _FakeAsyncClient.last_call()
    assert captured["url"].endswith("/v1/web-search")
    # 博查走 Authorization: Bearer，不需要 body 里的 api_key
    assert captured["headers"]["Authorization"] == "Bearer sk-bocha-test"
    assert "api_key" not in captured["json"]
    # 默认检索词要覆盖「必去 / 必玩」
    assert "北海" in captured["json"]["query"]
    assert "必去景点" in captured["json"]["query"]
    assert captured["json"]["count"] == 8
    assert captured["json"]["summary"] is True
    assert captured["json"]["freshness"] == "noLimit"

    assert result["city"] == "北海"
    assert result["total_matches"] == 1234
    assert result["sources"][0]["url"] == "https://example.com/beihai"
    assert "银滩适合看日落" in result["text"]
    assert "https://example.com/beihai" in result["text"]
    # 摘要需标明是「节选自各来源」，避免被当成模型生成的结论
    assert "节选自各来源" in result["text"]


@pytest.mark.asyncio
async def test_bocha_maps_fields_to_internal_shape(monkeypatch):
    """博查字段名（name/summary/datePublished/siteName）要被正确归一化"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(
                payload=_bocha_payload(
                    "北海 景点",
                    [_bocha_page("银滩", "https://a.com/b", summary="详细正文摘要", snippet="短摘要")],
                )
            )
        ]
    )

    result = await BochaClient().search_attractions("北海")
    item = result["results"][0]

    assert item["title"] == "银滩"          # name -> title
    assert item["url"] == "https://a.com/b"
    assert item["content"] == "详细正文摘要"  # summary 优先于 snippet
    assert item["snippet"] == "短摘要"
    assert item["site_name"] == "示例站点"
    assert item["published_date"] == "2026-09-01T00:00:00+08:00"


@pytest.mark.asyncio
async def test_bocha_falls_back_to_snippet_without_summary(monkeypatch):
    """summary=false 时博查只返回 snippet，不能因此拿不到内容"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(
                payload=_bocha_payload(
                    "北海 景点",
                    [_bocha_page("银滩", "https://a.com/b", summary="", snippet="仅短摘要")],
                )
            )
        ]
    )

    result = await BochaClient().search_attractions("北海")
    assert result["results"][0]["content"] == "仅短摘要"


@pytest.mark.asyncio
async def test_bocha_accepts_response_without_data_wrapper(monkeypatch):
    """兼容不带 data 包装的响应形态，避免因网关差异解析失败"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(
                payload={
                    "_type": "SearchResponse",
                    "webPages": {
                        "value": [_bocha_page("银滩", "https://a.com/b", summary="内容")],
                    },
                }
            )
        ]
    )

    result = await BochaClient().search_attractions("北海")
    assert result["results"][0]["title"] == "银滩"


@pytest.mark.asyncio
async def test_bocha_keyword_is_merged_into_query(monkeypatch):
    """keyword 是额外限定，不能顶掉「酒店 / 住宿」这类类别词"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_bocha_payload("q", [_bocha_page("占位", "https://a.com", summary="占位内容")]))])

    await BochaClient().search_hotels("丽江", keyword="海景民宿")

    query = _FakeAsyncClient.last_call()["json"]["query"]
    assert "丽江" in query
    assert "海景民宿" in query
    # 关键：类别词必须保留，否则会搜回房产等无关内容
    assert "酒店" in query
    assert "住宿" in query


@pytest.mark.asyncio
async def test_bocha_attractions_keeps_category_with_keyword(monkeypatch):
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_bocha_payload("q", [_bocha_page("占位", "https://a.com", summary="占位内容")]))])

    await BochaClient().search_attractions("北海", keyword="小众")

    query = _FakeAsyncClient.last_call()["json"]["query"]
    assert "北海" in query and "小众" in query
    assert "景点" in query


@pytest.mark.asyncio
async def test_bocha_hotels_use_tighter_freshness(monkeypatch):
    """酒店价格与口碑时效性强，默认限定一年内"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_bocha_payload("q", [_bocha_page("占位", "https://a.com", summary="占位内容")]))])

    await BochaClient().search_hotels("北海")

    assert _FakeAsyncClient.last_call()["json"]["freshness"] == "oneYear"


@pytest.mark.asyncio
async def test_bocha_count_is_capped_at_api_max(monkeypatch):
    """博查 count 上限为 50，超出的入参要被夹住"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_bocha_payload("q", [_bocha_page("占位", "https://a.com", summary="占位内容")]))])

    await BochaClient().search_attractions("北海", limit=100)
    assert _FakeAsyncClient.last_call()["json"]["count"] == 50


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("noLimit", "noLimit"),
        ("oneYear", "oneYear"),
        ("2026-01-01", "2026-01-01"),
        ("2026-01-01..2026-06-30", "2026-01-01..2026-06-30"),
        ("乱填的值", "noLimit"),   # 非法值退回默认，避免上游报错
        ("", "noLimit"),
    ],
)
def test_bocha_normalize_freshness(raw, expected):
    assert _normalize_freshness(raw) == expected


@pytest.mark.asyncio
async def test_bocha_raises_when_nothing_found(monkeypatch):
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    # 空结果才应触发「未检索到」，这里必须保持空
    _FakeAsyncClient.reset([_FakeResponse(payload=_bocha_payload("q", []))])

    with pytest.raises(ToolCallError):
        await BochaClient().search_attractions("不存在的城市")


@pytest.mark.asyncio
async def test_bocha_surfaces_error_code_in_body(monkeypatch):
    """博查失败时 HTTP 仍可能是 200，错误在 body 的 code / msg 里"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [_FakeResponse(payload={"code": 403, "msg": "Invalid API KEY", "data": None})]
    )

    with pytest.raises(ToolCallError) as exc:
        await BochaClient().search_attractions("北海")
    assert "403" in str(exc.value)
    assert "Invalid API KEY" in str(exc.value)


@pytest.mark.asyncio
async def test_bocha_surfaces_auth_error(monkeypatch):
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "bad-key")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(status_code=401, payload={"detail": "unauthorized"})])

    with pytest.raises(ToolCallError) as exc:
        await BochaClient().search_attractions("北海")
    assert "鉴权失败" in str(exc.value)


@pytest.mark.asyncio
async def test_bocha_403_reports_quota_not_just_bad_key(monkeypatch):
    """403 可能是余额/配额不足，不能一律误导成「Key 无效」"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-no-quota")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(
                status_code=403,
                payload={
                    "message": "You do not have enough money or package quota",
                    "code": "403",
                },
            )
        ]
    )

    with pytest.raises(ToolCallError) as exc:
        await BochaClient().search_attractions("北海")

    message = str(exc.value)
    assert "403" in message
    # 必须点出「余额/配额」这个真实原因，并透传上游原始说明
    assert "配额" in message or "余额" in message
    assert "You do not have enough money or package quota" in message


@pytest.mark.asyncio
async def test_bocha_composes_summary_from_top_sources(monkeypatch):
    """博查没有 answer 字段，摘要应由前几条来源节选拼接而成"""
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(
                payload=_bocha_payload(
                    "北海 景点",
                    [
                        _bocha_page("A", "https://a.com", summary="第一条摘要"),
                        _bocha_page("B", "https://b.com", summary="第二条摘要"),
                        _bocha_page("C", "https://c.com", summary="第三条摘要"),
                        _bocha_page("D", "https://d.com", summary="第四条摘要"),
                    ],
                )
            )
        ]
    )

    result = await BochaClient().search_attractions("北海")

    assert "第一条摘要" in result["answer"]
    assert "第三条摘要" in result["answer"]
    # 只取前 3 条拼接，避免摘要过长挤占 prompt
    assert "第四条摘要" not in result["answer"]


@pytest.mark.asyncio
async def test_search_attractions_tool_collects_and_returns_text(monkeypatch):
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [
            _FakeResponse(
                payload=_bocha_payload(
                    "北海 景点",
                    [_bocha_page("银滩", "https://a.com", summary="银滩是必去景点。")],
                )
            )
        ]
    )

    start_collector()
    payload = json.loads(await search_attractions.ainvoke({"city": "北海"}))

    assert payload["city"] == "北海"
    assert "银滩是必去景点" in payload["text"]
    assert payload["sources"][0]["url"] == "https://a.com"
    # 景点改走联网检索后不再返回坐标，行程规划需用景点名称
    assert "note" in payload

    collected = collector_module.get_collector().get("attractions")
    assert collected["city"] == "北海"


@pytest.mark.asyncio
async def test_search_hotels_tool_states_booking_boundary(monkeypatch):
    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", "sk-bocha-test")
    monkeypatch.setattr(bocha_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset(
        [_FakeResponse(payload=_bocha_payload("q", [_bocha_page("海景酒店", "https://a.com", summary="推荐海景房。")]))]
    )

    start_collector()
    payload = json.loads(await search_hotels.ainvoke({"city": "北海", "keyword": "海景"}))

    assert "不含实时房态与在线下单能力" in payload["note"]
    assert collector_module.get_collector().get("hotels")["city"] == "北海"


@pytest.mark.asyncio
async def test_guarded_tools_isolate_failures(monkeypatch):
    """两个工具都走博查时，缺 Key 的失败不能互相污染"""
    from app.agent.tools import SAFE_TOOLS
    from app.agent.tools.collector import get_collector

    monkeypatch.setattr(bocha_module.settings, "BOCHA_API_KEY", None)
    monkeypatch.setattr(amap_module.settings, "AMAP_API_KEY", "amap-test-key")
    monkeypatch.setattr(amap_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.reset([_FakeResponse(payload=_AMAP_GEO_OK), _FakeResponse(payload=_AMAP_WEATHER_OK)])

    guarded = {t.name: t for t in SAFE_TOOLS}
    start_collector()

    attractions_text = await guarded["search_attractions"].ainvoke({"city": "北海"})
    weather_text = await guarded["get_weather"].ainvoke({"city": "北海"})

    assert "search_attractions" in attractions_text
    assert "BOCHA_API_KEY" in attractions_text
    # 天气工具不受博查缺 Key 影响，仍返回真实结构化预报
    assert json.loads(weather_text)["forecasts"][0]["date"] == "2026-09-29"
    # 配置类错误被标记为本次请求内不可用，避免模型反复重试
    assert get_collector().is_unavailable("search_attractions")
