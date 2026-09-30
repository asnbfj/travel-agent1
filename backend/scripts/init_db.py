"""初始化数据库（创建所有表）"""
import asyncio
import os
import sys

# 允许直接以 `python scripts/init_db.py` 运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main():
    settings = get_settings()
    print(f"🔧 初始化数据库: {settings.DATABASE_URL}")
    # 导入模型以注册元数据
    import app.models  # noqa: F401

    await init_db()
    print("✅ 数据库表创建完成")


if __name__ == "__main__":
    asyncio.run(main())
