"""「保存到我的行程」接口测试

对应两个端点：
- `POST /api/v1/trips/plan/extract` 推断字段（弹窗预填，不落库）
- `POST /api/v1/trips/from-plan`    真正落库（含 generated_plan）

重点验证**闭环**：保存后从 `/api/v1/trips/{id}` 读回，`generated_plan`
里的正文与天气能完整取到——否则「我的行程」页会是一片空白。
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

PLAN_MD = """## 🌤 一、天气速览

北海未来三天多云，**适合下海**。数据发布于 2026-09-30 09:35:09。

## 🗺 二、3 天行程

### Day 1｜银滩看海 + 侨港吃海鲜
- **上午**：北海银滩。

### Day 2｜涠洲岛一日
- 鳄鱼山火山口地貌。

### Day 3｜老城与返程
- 北海老街。
"""

WEATHER = {
    "city": "北海",
    "source": "高德地图",
    "report_time": "2026-09-30 09:35:09",
    "tips": "气温较高，注意防暑防晒。",
    "forecasts": [
        {"date": "2026-09-30", "weekday": "周三", "weather": "多云", "icon": "⛅",
         "temp_low": 27, "temp_high": 32},
    ],
}

USER_MESSAGE = "我想去北海，3天，2人，预算3000，10月1日出发"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    name = f"plan_{uuid.uuid4().hex[:8]}"
    client.post("/api/v1/auth/register",
                json={"username": name, "email": f"{name}@example.com", "password": "123456"})
    resp = client.post("/api/v1/auth/login", data={"username": name, "password": "123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# --------------------------------------------------------------- 字段推断

def test_extract_returns_prefilled_fields(client, auth_headers):
    resp = client.post(
        "/api/v1/trips/plan/extract",
        json={
            "content": PLAN_MD,
            "weather_info": WEATHER,
            "tool_calls": [{"name": "get_weather", "args": {"city": "北海"}}],
            "user_message": USER_MESSAGE,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["destination"] == "北海"
    assert data["title"] == "北海 3 天行程"
    assert data["days_count"] == 3
    assert data["travelers"] == 2
    assert data["budget"] == 3000
    # 用户说的「10 月 1 日」+ 3 天 => 10/1 ~ 10/3
    assert data["start_date"] == "2026-10-01"
    assert data["end_date"] == "2026-10-03"


def test_extract_does_not_persist_anything(client, auth_headers):
    """推断接口不能顺手把行程存进库"""
    before = len(client.get("/api/v1/trips", headers=auth_headers).json())
    client.post("/api/v1/trips/plan/extract",
                json={"content": PLAN_MD}, headers=auth_headers)
    after = len(client.get("/api/v1/trips", headers=auth_headers).json())
    assert after == before


def test_extract_requires_auth(client):
    assert client.post("/api/v1/trips/plan/extract",
                       json={"content": PLAN_MD}).status_code == 401


def test_extract_rejects_empty_content(client, auth_headers):
    resp = client.post("/api/v1/trips/plan/extract", json={"content": ""}, headers=auth_headers)
    assert resp.status_code == 422


# --------------------------------------------------------------- 保存行程

def test_save_from_plan_creates_trip_with_generated_plan(client, auth_headers):
    resp = client.post(
        "/api/v1/trips/from-plan",
        json={
            "title": "北海 3 天行程",
            "destination": "北海",
            "start_date": "2026-10-01",
            "end_date": "2026-10-03",
            "budget": 3000,
            "travelers": 2,
            "content": PLAN_MD,
            "weather_info": WEATHER,
            "source_message": USER_MESSAGE,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    trip = resp.json()
    assert trip["title"] == "北海 3 天行程"
    assert trip["destination"] == "北海"
    assert trip["travelers"] == 2
    assert trip["budget"] == 3000

    plan = trip["generated_plan"]
    assert plan["content"] == PLAN_MD
    assert plan["weather_info"]["city"] == "北海"
    assert plan["source_message"] == USER_MESSAGE
    assert plan["generated_at"]


def test_saved_trip_is_readable_via_detail_endpoint(client, auth_headers):
    """闭环：保存后从详情接口读回，正文与天气都在（否则「我的行程」是空白）"""
    created = client.post(
        "/api/v1/trips/from-plan",
        json={
            "title": "东京 5 天赏樱", "destination": "东京",
            "start_date": "2027-04-01", "end_date": "2027-04-05",
            "travelers": 2, "budget": 20000,
            "content": PLAN_MD, "weather_info": WEATHER,
        },
        headers=auth_headers,
    ).json()

    fetched = client.get(f"/api/v1/trips/{created['id']}", headers=auth_headers)
    assert fetched.status_code == 200
    plan = fetched.json()["generated_plan"]
    assert plan["content"] == PLAN_MD
    assert plan["weather_info"]["tips"] == "气温较高，注意防暑防晒。"


def test_saved_trip_appears_in_list(client, auth_headers):
    created = client.post(
        "/api/v1/trips/from-plan",
        json={
            "title": "列表可见性验证", "destination": "北海",
            "start_date": "2026-10-01", "end_date": "2026-10-03",
            "content": PLAN_MD,
        },
        headers=auth_headers,
    ).json()

    listed = client.get("/api/v1/trips", headers=auth_headers).json()
    assert any(t["id"] == created["id"] for t in listed)


def test_save_from_plan_accepts_missing_weather(client, auth_headers):
    """天气是可选的：只查了景点没查天气时也应能保存"""
    resp = client.post(
        "/api/v1/trips/from-plan",
        json={
            "title": "无天气行程", "destination": "大理",
            "start_date": "2026-11-01", "end_date": "2026-11-03",
            "content": "# 大理三日\n\n正文",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["generated_plan"]["weather_info"] is None


def test_save_from_plan_requires_auth(client):
    resp = client.post("/api/v1/trips/from-plan", json={
        "title": "T", "destination": "北海",
        "start_date": "2026-10-01", "end_date": "2026-10-03", "content": "x",
    })
    assert resp.status_code == 401


@pytest.mark.parametrize("patch,reason", [
    ({"content": ""}, "正文为空"),
    ({"title": ""}, "标题为空"),
    ({"destination": ""}, "目的地为空"),
    ({"end_date": "2026-09-01"}, "返回日期早于出发日期"),
    ({"start_date": "not-a-date"}, "日期格式非法"),
])
def test_save_from_plan_validates_payload(client, auth_headers, patch, reason):
    payload = {
        "title": "北海 3 天行程", "destination": "北海",
        "start_date": "2026-10-01", "end_date": "2026-10-03",
        "content": PLAN_MD,
    }
    payload.update(patch)
    resp = client.post("/api/v1/trips/from-plan", json=payload, headers=auth_headers)
    assert resp.status_code == 422, f"{reason} 应被拒绝"


def test_saved_plan_can_be_exported_as_pdf(client, auth_headers):
    """两个功能能串起来：保存到我的行程 → 导出行程 PDF"""
    trip = client.post(
        "/api/v1/trips/from-plan",
        json={
            "title": "北海 3 天行程", "destination": "北海",
            "start_date": "2026-10-01", "end_date": "2026-10-03",
            "content": PLAN_MD, "weather_info": WEATHER,
        },
        headers=auth_headers,
    ).json()

    resp = client.post(
        "/api/v1/agent/export/pdf",
        json={"content": trip["generated_plan"]["content"],
              "title": trip["title"],
              "weather_info": trip["generated_plan"]["weather_info"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
