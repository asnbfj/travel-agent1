"""工具层异常定义

线上模式下所有工具都必须「要么返回真实数据，要么明确报错」，
绝不返回任何模拟/占位数据。因此这里定义可区分的异常类型，
便于 Agent 把「缺 Key」这类配置问题和「上游接口报错」区分开，
并把可操作的信息透传给用户。
"""
from typing import Optional, Any
import httpx

_AMAP_INFOCODE_HINTS = {
    "10001": "高德 Key 无效（INVALID_USER_KEY），请检查 AMAP_API_KEY",
    "10002": "高德 Key 已过期或被禁用",
    "10003": "高德 Key 今日配额已用尽（DAILY_QUERY_OVER_LIMIT）",
    "10004": "高德 Key 访问过于频繁，请稍后重试",
    "10009": "高德 Key 平台类型不匹配（USERKEY_PLAT_NOMATCH），请在控制台确认 Key 绑定的是「Web服务」",
    "10012": "高德账号未开通该服务（INSUFFICIENT_PRIVILEGES），请在控制台开通对应权限",
    "10013": "高德 Key 已被删除或不存在",
    "10021": "高德请求 QPS 超限（CUQPS_HAS_EXCEEDED_THE_LIMIT），已自动限速重试；若持续出现请调大 AMAP_MIN_INTERVAL",
    "10019": "高德请求 QPS 超限（CUQPS_HAS_EXCEEDED_THE_LIMIT）",
    "20800": "高德请求参数错误（缺少必填参数）",
    "20803": "高德坐标格式错误，需为「经度,纬度」",
}


class ToolConfigError(RuntimeError):
    """配置缺失：缺少 API Key 等。属于开发者/部署问题，需明确暴露。"""

    def __init__(self, tool: str, missing: str, hint: str = "") -> None:
        self.tool = tool
        self.missing = missing
        message = f"[{tool}] 缺少必需配置 {missing}"
        if hint:
            message += f"。{hint}"
        super().__init__(message)


class ToolCallError(RuntimeError):
    """上游接口调用失败：网络错误 / 鉴权失败 / 业务错误码。"""

    def __init__(self, tool: str, detail: str, status_code: Optional[int] = None) -> None:
        self.tool = tool
        self.detail = detail
        self.status_code = status_code
        super().__init__(f"[{tool}] {detail}")


def require_key(tool: str, key: Optional[str], name: str, hint: str = "") -> str:
    """校验必需的 API Key，缺失时抛出 ToolConfigError"""
    if not key or not str(key).strip():
        raise ToolConfigError(tool, name, hint)
    return str(key).strip()


def raise_for_http(tool: str, response: httpx.Response) -> None:
    """把上游 HTTP 错误转成可读的 ToolCallError"""
    if response.status_code == 200:
        return
    if response.status_code in (401, 403):
        raise ToolCallError(
            tool, f"鉴权失败（HTTP {response.status_code}），请检查 API Key 是否有效", response.status_code
        )
    if response.status_code == 429:
        raise ToolCallError(tool, "请求过于频繁（HTTP 429），请稍后重试", 429)
    raise ToolCallError(
        tool, f"上游返回 HTTP {response.status_code}: {response.text[:200]}", response.status_code
    )


def raise_for_amap(tool: str, payload: Any) -> None:
    """校验高德响应体中的 status / infocode"""
    if not isinstance(payload, dict):
        raise ToolCallError(tool, "高德返回了非预期的响应格式")
    if str(payload.get("status")) == "1":
        return

    infocode = str(payload.get("infocode", ""))
    info = str(payload.get("info", "未知错误"))
    hint = _AMAP_INFOCODE_HINTS.get(infocode, "")
    detail = f"高德接口报错 {info}({infocode})"
    if hint:
        detail += f"：{hint}"
    raise ToolCallError(tool, detail)


def format_tool_error(tool_name: str, error: Exception) -> str:
    """把工具异常转成给模型看的、对用户可操作的说明

    - 明确带上工具名，避免多个工具并行失败时被模型混为一谈
    - 结尾附上「不要重试」指令：模型倾向于反复重试失败的工具，既慢又容易张冠李戴
    """
    if isinstance(error, ToolConfigError):
        detail = f"{error}。这是部署配置问题，需要在 backend/.env 中补齐后重启服务。"
    elif isinstance(error, ToolCallError):
        detail = f"{error}。请检查该 API Key 的配额与权限，或稍后再试。"
    else:
        detail = f"{type(error).__name__}: {error}"

    return (
        f"工具「{tool_name}」调用失败：{detail}"
        f"【重要】该工具本轮已失败，请勿重复调用，直接向用户如实说明即可。"
    )
