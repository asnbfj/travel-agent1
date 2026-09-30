"""API 接口测试"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["app"] == "TravelAI"


def test_register_and_login(client):
    username = f"tester_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"

    # 注册
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "123456"},
    )
    assert resp.status_code == 201
    assert resp.json()["username"] == username

    # 登录
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": "123456"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token

    # 获取当前用户
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == username


def test_login_wrong_password(client):
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": "not_exist", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_agent_chat_requires_auth(client):
    resp = client.post("/api/v1/agent/chat", json={"message": "我想去东京"})
    assert resp.status_code == 401
