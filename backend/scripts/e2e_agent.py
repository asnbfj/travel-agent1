"""端到端全链路验证：HTTP API -> Agent -> LLM -> 真实工具

覆盖三种典型场景，检验多工具编排与结构化结果回传。
用法：python scripts/e2e_agent.py
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8899")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCENARIOS = [
    ("单工具·天气", "北海明天天气怎么样？适合下海玩水吗？"),
    ("多工具·行程规划", "帮我规划北海3天行程，2个人，想看海和吃海鲜，顺便告诉我天气和住哪方便"),
]


async def main() -> int:
    # trust_env=False：只访问本机后端，避免系统代理（HTTP_PROXY 等）把请求接走
    async with httpx.AsyncClient(base_url=BASE, timeout=300, trust_env=False) as client:
        # 1) 注册（已存在则忽略）
        creds = {"username": "e2e_tester", "email": "e2e@example.com", "password": "e2e-pass-123"}
        r = await client.post("/api/v1/auth/register", json=creds)
        print(f"[注册] {r.status_code} {'已存在' if r.status_code >= 400 else '成功'}")

        # 2) 登录
        r = await client.post(
            "/api/v1/auth/login",
            data={"username": creds["username"], "password": creds["password"]},
        )
        if r.status_code >= 400:
            print(f"[登录] 失败 {r.status_code}: {r.text[:300]}")
            return 1
        token = r.json().get("access_token")
        print("[登录] 成功")
        headers = {"Authorization": f"Bearer {token}"}

        # 3) 语义化问句，逐个场景验证
        failed = 0
        for label, message in SCENARIOS:
            print("\n" + "=" * 78)
            print(f"▶ [{label}]")
            print(f"  Q: {message}")

            started = time.time()
            try:
                resp = await client.post(
                    "/api/v1/agent/chat", json={"message": message}, headers=headers
                )
            except httpx.TimeoutException:
                print("  ❌ 请求超时（>300s）")
                failed += 1
                continue
            elapsed = time.time() - started

            if resp.status_code >= 400:
                print(f"  ❌ HTTP {resp.status_code}: {resp.text[:400]}")
                failed += 1
                continue

            data = resp.json()
            calls = data.get("tool_calls") or []
            print(f"  ⏱  耗时 {elapsed:.1f}s")
            print(f"  🔧 调用工具: {[c['name'] for c in calls]}")
            for call in calls:
                print(f"       - {call['name']}({json.dumps(call['args'], ensure_ascii=False)})")

            weather = data.get("weather_info")
            if weather:
                print(f"  🌤 天气卡片: {weather['city']} / 来源 {weather.get('source')} "
                      f"/ 发布 {weather.get('report_time')}")
                for day in weather.get("forecasts") or []:
                    print(f"       {day['date']} {day['weekday']} {day['icon']} {day['weather']} "
                          f"{day['temp_low']}~{day['temp_high']}°C {day['wind']}")
                if weather.get("tips"):
                    print(f"       💡 {weather['tips']}")

            answer = data.get("message") or ""
            print("  💬 回复:")
            for line in answer.splitlines()[:28]:
                print(f"       {line}")

            if not calls:
                print("  ❌ 未调用任何工具（应当调用）")
                failed += 1
            elif any(k in answer for k in ("调用失败", "无法完成查询")):
                print("  ❌ 回复中包含工具失败信息")
                failed += 1
            else:
                print("  ✅ 通过")

        print("\n" + "=" * 78)
        print(f"结果：{len(SCENARIOS) - failed}/{len(SCENARIOS)} 场景通过")
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
