"""应用程序配置"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""

    # 应用基础配置
    APP_NAME: str = "TravelAI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 数据库配置
    DATABASE_URL: str = "sqlite+aiosqlite:///./travelai.db"
    # PostgreSQL 生产环境使用
    # DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/travelai"

    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天

    # LLM 配置
    LLM_PROVIDER: str = "deepseek"  # openai / deepseek / qwen
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_TEMPERATURE: float = 0.7
    # 注意：新版推理模型（如 deepseek-flash / deepseek-v4-pro）的思维链会占用 completion 额度，
    # 设置过小会导致 content 为空且 finish_reason=length。实测 2000/4000 会返回空内容，需 >= 8000。
    OPENAI_MAX_TOKENS: int = 16000
    # 推理强度（low / high / max），仅对支持该参数的推理模型生效；留空则不传
    REASONING_EFFORT: str = "low"
    # 单次 LLM 调用超时（秒）——推理模型单次可能耗时数十秒
    LLM_TIMEOUT: int = 240

    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL: str = "deepseek-flash"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"

    QWEN_API_KEY: Optional[str] = None
    QWEN_MODEL: str = "qwen-max"
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 说明：项目采用「大模型 + 线上工具调用」架构，景点/酒店/天气/路线全部实时调用线上 API。
    # 原 RAG（向量检索）方案与 app/rag 模块已彻底移除，celery/redis 异步队列也已移除。

    # ===== 外部数据源（线上模式：全部为真实 API，不再有任何模拟数据）=====
    # 高德地图：路线规划 + POI 搜索（景点 / 酒店）
    # 申请地址 https://console.amap.com/dev/key/app
    AMAP_API_KEY: Optional[str] = None
    AMAP_BASE_URL: str = "https://restapi.amap.com/v3"
    AMAP_TIMEOUT: int = 15
    # 高德按 Key 限制 QPS，而 Agent 会并行调用多个工具（每个 plan_route 还要额外做 2 次地理编码），
    # 因此这里对同 Key 的所有请求做全局串行限速，避免触发 10021（CUQPS 超限）
    AMAP_MIN_INTERVAL: float = 0.34
    # 命中 QPS 限流时的重试次数（指数退避）
    AMAP_QPS_RETRY: int = 2

    # 博查 AI 搜索（https://open.bochaai.com）
    # 用于「景点 / 必玩地点 / 酒店住宿」的联网搜索
    # （天气与路线规划使用高德地图接口，见 AMAP_*）
    BOCHA_API_KEY: Optional[str] = None
    BOCHA_BASE_URL: str = "https://api.bochaai.com"
    BOCHA_SEARCH_PATH: str = "/v1/web-search"
    # 是否返回网页正文摘要（summary），检索质量更好
    BOCHA_SUMMARY: bool = True
    # 单次返回条数，博查上限 50（默认 8）
    BOCHA_COUNT: int = 8
    # 时间范围：noLimit / oneDay / oneWeek / oneMonth / oneYear
    # 景点用不限时间；酒店价格与口碑时效性强，默认限定一年内
    BOCHA_FRESHNESS: str = "noLimit"
    BOCHA_HOTEL_FRESHNESS: str = "oneYear"
    BOCHA_TIMEOUT: int = 30

    # 严格线上模式：缺少 Key / 调用失败时抛出明确错误，绝不返回模拟数据
    STRICT_ONLINE: bool = True

    # CORS 配置
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """获取配置（单例）"""
    return Settings()
