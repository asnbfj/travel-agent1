"""工具结构化结果收集器

LLM 看到的工具返回是文本，但前端需要结构化数据（例如天气卡片）。
这里用 contextvar 在单次请求内收集工具的真实返回结果，
供 API 层直接读取，避免让 LLM「转述」结构化数据而引入幻觉。
"""
from contextvars import ContextVar
from typing import Dict, Any, Optional, List


class ToolResultCollector:
    """单次请求内的工具结果收集器"""

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.calls: List[Dict[str, Any]] = []
        # 本次请求内已确定不可用的工具（例如缺 API Key）
        self.unavailable: set = set()

    def record(self, key: str, value: Any) -> None:
        """记录结构化结果（同名工具后一次覆盖前一次之外，也保留历史）"""
        self.data[key] = value

    def record_call(self, name: str, args: Dict[str, Any]) -> None:
        self.calls.append({"name": name, "args": args})

    def mark_unavailable(self, name: str) -> None:
        """标记工具在本次请求内不可用（配置缺失等无法通过重试恢复的原因）"""
        self.unavailable.add(name)

    def is_unavailable(self, name: str) -> bool:
        return name in self.unavailable

    def get(self, key: str) -> Optional[Any]:
        return self.data.get(key)

    def to_dict(self) -> Dict[str, Any]:
        return {"data": self.data, "calls": self.calls}


_collector: ContextVar[Optional[ToolResultCollector]] = ContextVar("tool_result_collector", default=None)


def start_collector() -> ToolResultCollector:
    """开始一次收集（每个请求调用一次）"""
    collector = ToolResultCollector()
    _collector.set(collector)
    return collector


def get_collector() -> Optional[ToolResultCollector]:
    return _collector.get()


def collect(key: str, value: Any) -> None:
    """记录结构化结果（无收集器时静默忽略）"""
    collector = _collector.get()
    if collector is not None:
        collector.record(key, value)


def collect_call(name: str, args: Dict[str, Any]) -> None:
    """记录一次工具调用（用于前端展示「已调用哪些工具」）"""
    collector = _collector.get()
    if collector is not None:
        collector.record_call(name, args)
