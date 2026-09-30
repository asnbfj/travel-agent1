"""LLM 客户端（OpenAI / DeepSeek / Qwen 可切换）

线上模式：
- 必须配置对应供应商的 API Key，否则启动/调用阶段直接抛出明确错误
- 不再提供离线 MockLLM 降级（原模拟实现已移除）
"""
from typing import Optional, Any, List, Dict
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

try:  # langchain_openai 缺失时给出明确错误
    from langchain_openai import ChatOpenAI as _ChatOpenAIBase
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "缺少依赖 langchain-openai，请先执行：pip install -r requirements.txt"
    ) from e

# 全局单例
_llm_client: Optional[Any] = None


class LLMConfigError(RuntimeError):
    """LLM 配置缺失：缺少 API Key 等"""


def _resolve_provider() -> str:
    """解析当前使用的 LLM 供应商"""
    return (settings.LLM_PROVIDER or "deepseek").lower()


def _provider_api_key(provider: str) -> Optional[str]:
    """获取指定供应商的 API Key"""
    if provider == "openai":
        return settings.OPENAI_API_KEY
    if provider == "qwen":
        return settings.QWEN_API_KEY
    return settings.DEEPSEEK_API_KEY


def _provider_model_and_base(provider: str) -> tuple:
    if provider == "openai":
        return settings.OPENAI_MODEL, settings.OPENAI_BASE_URL
    if provider == "qwen":
        return settings.QWEN_MODEL, settings.QWEN_BASE_URL
    return settings.DEEPSEEK_MODEL, settings.DEEPSEEK_BASE_URL


def check_llm_config() -> None:
    """校验 LLM 配置，缺失时抛出明确错误（供启动阶段与 API 层调用）"""
    provider = _resolve_provider()
    if provider not in ("openai", "deepseek", "qwen"):
        raise LLMConfigError(
            f"LLM_PROVIDER 取值非法：{provider}，可选 openai / deepseek / qwen"
        )
    key_name = {
        "openai": "OPENAI_API_KEY",
        "qwen": "QWEN_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }[provider]
    if not _provider_api_key(provider):
        raise LLMConfigError(
            f"未配置 {key_name}（当前 LLM_PROVIDER={provider}）。"
            f"请在 backend/.env 中填入有效的 API Key 后重启服务"
        )


def _make_chat_openai(model: str, api_key: str, base_url: str, max_tokens: int) -> Any:
    """构造 ChatOpenAI 客户端（带空内容兜底）"""
    # 推理模型（deepseek-flash 等）思维链占用 completion 额度，
    # 通过 reasoning_effort 降低强度可显著减少耗时与 token 消耗。
    model_kwargs: Dict[str, Any] = {}
    effort = (settings.REASONING_EFFORT or "").strip().lower()
    if effort in ("low", "medium", "high", "max"):
        model_kwargs["extra_body"] = {"reasoning_effort": effort}

    return ResilientChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=settings.OPENAI_TEMPERATURE,
        max_tokens=max_tokens,
        timeout=settings.LLM_TIMEOUT,
        max_retries=2,
        model_kwargs=model_kwargs,
    )


def _result_text(result: Any) -> str:
    """从 LLMResult 中取出文本"""
    try:
        return result.generations[0][0].text or ""
    except Exception:
        return ""


def _normalize_chat_inputs(messages: Any) -> List[Any]:
    """把 ``List[str]`` 风格的调用归一化为 LangChain 需要的 ``List[List[BaseMessage]]``

    LangChain 的 ``BaseChatModel.agenerate`` 要求「消息列表的列表」，
    传 ``[prompt]``（字符串）会被逐字符当作消息处理，
    报出 ``TypeError: Got unknown type 分`` 这类错误。
    这里统一兼容：
    - ``"prompt"``             -> ``[[HumanMessage(...)]]``
    - ``["prompt"]``           -> ``[[HumanMessage(...)]]``
    - ``[["prompt"]]``         -> ``[[HumanMessage(...)]]``
    - ``[[HumanMessage(...)]]``-> 原样返回
    """
    from langchain_core.messages import BaseMessage, HumanMessage

    def to_message(item: Any) -> Any:
        if isinstance(item, BaseMessage):
            return item
        return HumanMessage(content=str(item))

    if isinstance(messages, str):
        return [[HumanMessage(content=messages)]]
    if isinstance(messages, BaseMessage):
        return [[messages]]
    if not isinstance(messages, (list, tuple)):
        return [[HumanMessage(content=str(messages))]]

    normalized: List[Any] = []
    for item in messages:
        if isinstance(item, (list, tuple)):
            normalized.append([to_message(sub) for sub in item])
        else:
            normalized.append([to_message(item)])
    return normalized


class ResilientChatOpenAI(_ChatOpenAIBase):
    """输入归一化 + 空内容兜底

    1. 输入归一化：兼容 ``agenerate([prompt])`` 这种字符串调用方式。
    2. 空内容兜底：推理模型的思维链会占用 completion 额度（max_tokens）。额度偏小时
       接口仍返回 200，但 ``content`` 为空且 ``finish_reason=length``，最终会生成一份
       空白回复。这里检测到空内容时自动放大预算重试一次，并打印可操作的日志。
    """

    async def agenerate(self, messages: Any, stop: Any = None, callbacks: Any = None, **kwargs: Any) -> Any:
        normalized = _normalize_chat_inputs(messages)
        result = await super().agenerate(normalized, stop=stop, callbacks=callbacks, **kwargs)
        if _result_text(result).strip() or _has_tool_calls(result):
            return result

        logger.error(
            "⚠ LLM 返回空内容（finish_reason 通常为 length）："
            "推理模型的思维链占满了 max_tokens。请调大 OPENAI_MAX_TOKENS 或降低 REASONING_EFFORT。"
        )
        current = self.max_tokens or settings.OPENAI_MAX_TOKENS
        if current >= 32000:
            return result

        new_limit = min(current * 2, 64000)
        logger.warning(f"↻ 以 max_tokens={new_limit} 重试一次")
        key = self.openai_api_key
        if hasattr(key, "get_secret_value"):
            key = key.get_secret_value()
        bigger = _make_chat_openai(
            str(self.model_name), str(key), str(self.openai_api_base or ""), new_limit
        )
        return await bigger.agenerate(normalized, stop=stop, callbacks=callbacks, **kwargs)


def _has_tool_calls(result: Any) -> bool:
    """判断 LLMResult 中是否包含工具调用（有工具调用时 content 为空是正常的）"""
    try:
        message = result.generations[0][0].message
        return bool(getattr(message, "tool_calls", None))
    except Exception:
        return False


def _build_llm() -> Any:
    """根据配置构建 LangChain Chat 模型客户端（严格线上）"""
    check_llm_config()
    provider = _resolve_provider()
    model, base_url = _provider_model_and_base(provider)
    api_key = _provider_api_key(provider)

    logger.info(f"🤖 初始化 LLM 客户端: provider={provider}, model={model}")
    return _make_chat_openai(model, str(api_key), str(base_url), settings.OPENAI_MAX_TOKENS)


def get_llm_client() -> Any:
    """获取 LLM 客户端（单例）

    未配置 API Key 时抛出 LLMConfigError，不再降级为模拟实现。
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = _build_llm()
    return _llm_client


def reset_llm_client() -> None:
    """重置单例（配置变更后使用）"""
    global _llm_client
    _llm_client = None
