"""FastAPI 入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.api import api_router
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info(f"🚀 启动 {settings.APP_NAME} v{settings.APP_VERSION}")

    # 应用网页端保存的配置覆盖（runtime_config.json > .env）。
    # 必须排在下面的配置自检之前：否则自检读到的仍是 .env 的旧值，
    # 会在日志里报出「缺 Key」这类与实际生效配置不符的误导信息。
    from app.runtime_config import apply_overrides
    apply_overrides()

    # 导入模型以注册元数据
    import app.models  # noqa: F401
    await init_db()
    logger.info("✅ 数据库初始化完成")

    # 线上模式配置自检：缺 Key 时在启动日志中明确提示（不再有模拟数据兜底）
    from app.llm.client import check_llm_config, LLMConfigError
    from app.agent.graph import check_tool_config

    try:
        check_llm_config()
        logger.info("✅ LLM 配置校验通过")
    except LLMConfigError as e:
        logger.error(f"❌ LLM 配置校验失败：{e}")

    missing_tools = check_tool_config()
    if missing_tools:
        logger.error("❌ 以下线上工具缺少 API Key，相关功能将直接报错：")
        for item in missing_tools:
            logger.error(f"   - {item}")
    else:
        logger.info("✅ 线上工具配置校验通过（高德地图 / 博查 AI 搜索）")

    yield
    logger.info("👋 应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="智能旅行规划 Agent - 基于 LLM 工具调用（Function Calling）/ LangGraph，实时调用线上 API",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router)


@app.get("/", tags=["系统"])
async def root():
    """根路径"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health", tags=["系统"])
async def health():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
