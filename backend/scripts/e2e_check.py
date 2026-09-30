"""端到端工具验证脚本（真实调用线上 API，不 mock）

用法：cd backend && python scripts/e2e_check.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.tools import ALL_TOOLS, start_collector  # noqa: E402

CASES = [
    ("get_weather", {"city": "北海", "days": 3}, "高德·天气"),
    ("search_attractions", {"city": "北海", "keyword": "银滩", "limit": 5}, "博查·景点"),
    ("search_hotels", {"city": "北海", "keyword": "海景", "limit": 5}, "博查·酒店"),
    ("plan_route", {"origin": "北海银滩", "destination": "北海老街", "mode": "driving", "city": "北海"}, "高德·路线"),
]


async def main() -> int:
    tools = {t.name: t for t in ALL_TOOLS}
    start_collector()
    failed = 0

    for name, args, label in CASES:
        print("=" * 72)
        print(f"▶ [{label}] {name}({json.dumps(args, ensure_ascii=False)})")
        try:
            raw = await tools[name].ainvoke(args)
            parsed = json.loads(raw)
            text = parsed.get("text") or raw
            print(text[:1400])
            if "调用失败" in raw:
                print("❌ 工具返回失败")
                failed += 1
            else:
                print("✅ 通过")
        except Exception as e:  # noqa: BLE001
            print(f"❌ 异常 {type(e).__name__}: {e}")
            failed += 1
        print()

    print("=" * 72)
    print("结构化结果（供前端卡片 / 展示）:")
    collector = __import__("app.agent.tools.collector", fromlist=["get_collector"]).get_collector()
    for key, value in collector.data.items():
        summary = json.dumps(value, ensure_ascii=False)
        print(f"  - {key}: {summary[:300]}")
    print(f"\n工具调用记录: {json.dumps(collector.calls, ensure_ascii=False)}")

    print("=" * 72)
    print(f"结果：{len(CASES) - failed}/{len(CASES)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
