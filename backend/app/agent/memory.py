"""Agent 记忆管理（对话历史）"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

# 内存存储（开发/兜底）。生产环境可切换到 Redis / 数据库。
_MEMORY_STORE: Dict[str, List[Dict[str, Any]]] = {}


def _new_id() -> str:
    return str(uuid.uuid4())


async def save_message(
    user_id: str,
    role: str,
    content: str,
    db: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    保存一条对话消息

    Args:
        user_id: 用户 ID
        role: 角色（user / assistant）
        content: 消息内容
        db: 数据库会话（可选，预留持久化）
        metadata: 附加元数据

    Returns:
        保存的消息
    """
    message = {
        "id": _new_id(),
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": metadata or {},
    }
    _MEMORY_STORE.setdefault(str(user_id), []).append(message)
    logger.debug(f"💾 保存消息 [{role}] user={user_id}")
    return message


async def get_conversation_history(
    user_id: str,
    db: Any = None,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """获取对话历史（按时间正序）"""
    history = _MEMORY_STORE.get(str(user_id), [])
    # 取最近 limit + offset 条，再截断 offset
    sliced = history[offset: offset + limit]
    return [dict(m) for m in sliced]


async def clear_conversation_history(user_id: str, db: Any = None) -> int:
    """清除对话历史，返回清除条数"""
    history = _MEMORY_STORE.pop(str(user_id), [])
    return len(history)


async def get_memory(user_id: str) -> Dict[str, Any]:
    """获取用户记忆摘要"""
    history = _MEMORY_STORE.get(str(user_id), [])
    return {
        "user_id": user_id,
        "message_count": len(history),
        "last_message": history[-1] if history else None,
    }
