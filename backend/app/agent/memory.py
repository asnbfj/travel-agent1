"""Agent 记忆管理（会话与对话历史）

聊天记录落库到 `conversations` / `conversation_messages`，按会话隔离。

> 早期实现把历史存在进程内字典里（按 user_id 索引），有两个问题：
> 1. 进程重启即丢，无法作为「历史咨询」稳定回看；
> 2. 没有会话概念，几次无关的咨询会混进同一段上下文交给大模型。
"""
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import re
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.conversation import Conversation, ConversationMessage

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "新对话"
# 自动标题的最大字数
TITLE_MAX_CHARS = 30


class ConversationNotFound(Exception):
    """会话不存在或不属于当前用户"""


def derive_title(text: str) -> str:
    """由首条提问生成会话标题

    提问里常带 Markdown 标记与多余空白，先清理再截断；截断时加省略号，
    避免标题看起来像是被硬切掉的半句话。
    """
    cleaned = re.sub(r"[#*`>\-\[\]]+", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return DEFAULT_TITLE
    if len(cleaned) <= TITLE_MAX_CHARS:
        return cleaned
    return cleaned[:TITLE_MAX_CHARS].rstrip() + "…"


@asynccontextmanager
async def _session(db: Optional[AsyncSession]):
    """复用调用方的会话；没有则临时开一个

    Agent 运行时（`graph.py`）手上没有请求级会话，所以这里允许自建，
    用完即关，不把连接泄漏到调用方。
    """
    if db is not None:
        yield db
    else:
        async with AsyncSessionLocal() as own:
            yield own


async def create_conversation(
    db: AsyncSession, user_id: str, title: Optional[str] = None
) -> Conversation:
    """新建会话"""
    conversation = Conversation(
        user_id=uuid.UUID(str(user_id)),
        title=(title or "").strip() or DEFAULT_TITLE,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    logger.info("🗂 新建会话 %s（用户 %s）", conversation.id, user_id)
    return conversation


async def get_conversation(
    db: AsyncSession, user_id: str, conversation_id: str
) -> Optional[Conversation]:
    """取会话（带归属校验，避免越权读到他人会话）"""
    try:
        cid = uuid.UUID(str(conversation_id))
    except (ValueError, AttributeError, TypeError):
        return None
    return await db.scalar(
        select(Conversation).where(
            Conversation.id == cid,
            Conversation.user_id == uuid.UUID(str(user_id)),
        )
    )


async def append_message(
    db: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    meta: Optional[Dict[str, Any]] = None,
) -> ConversationMessage:
    """往会话里追加一条消息；首条用户消息会顺带生成标题"""
    cid = uuid.UUID(str(conversation_id))
    conversation = await db.scalar(select(Conversation).where(Conversation.id == cid))
    if conversation is None:
        raise ConversationNotFound(str(conversation_id))

    # 先判断是否为「首条用户消息」：此时新消息还没入库，count 里不含它
    is_first_user_message = False
    if role == "user":
        existing = await db.scalar(
            select(func.count())
            .select_from(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == cid,
                ConversationMessage.role == "user",
            )
        )
        is_first_user_message = not existing

    message = ConversationMessage(
        conversation_id=cid, role=role, content=content, meta=meta or {}
    )
    db.add(message)

    if is_first_user_message:
        conversation.title = derive_title(content)
    # 追加消息不会触碰会话行，onupdate 不会触发，需显式刷新用于「最近使用」排序
    conversation.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(message)
    return message


async def list_conversations(
    db: AsyncSession, user_id: str, limit: int = 50, offset: int = 0
) -> List[Dict[str, Any]]:
    """列出会话（按最近使用倒序），附带消息数与预览

    消息数与预览用相关子查询一次取出，避免逐条再查一遍（N+1）。
    """
    last_content = (
        select(ConversationMessage.content)
        .where(ConversationMessage.conversation_id == Conversation.id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    message_count = (
        select(func.count(ConversationMessage.id))
        .where(ConversationMessage.conversation_id == Conversation.id)
        .scalar_subquery()
    )

    rows = await db.execute(
        select(Conversation, last_content, message_count)
        .where(Conversation.user_id == uuid.UUID(str(user_id)))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )

    out: List[Dict[str, Any]] = []
    for conversation, preview, count in rows.all():
        out.append(
            {
                "id": str(conversation.id),
                "title": conversation.title,
                "created_at": conversation.created_at,
                "updated_at": conversation.updated_at,
                "message_count": int(count or 0),
                "preview": _excerpt(preview),
            }
        )
    return out


async def count_conversations(db: AsyncSession, user_id: str) -> int:
    """当前用户的会话总数（用于列表分页）"""
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == uuid.UUID(str(user_id)))
        )
        or 0
    )


def _excerpt(text: Optional[str], limit: int = 60) -> str:
    """把消息正文压成一行摘要（去掉 Markdown 标记与换行）"""
    if not text:
        return ""
    cleaned = re.sub(r"[#*`>\-]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


async def get_messages(
    db: AsyncSession, conversation_id: str, limit: int = 200, offset: int = 0
) -> List[Dict[str, Any]]:
    """按时间正序取会话消息"""
    rows = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == uuid.UUID(str(conversation_id)))
        .order_by(ConversationMessage.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return [_message_to_dict(m) for m in rows.scalars().all()]


def _message_to_dict(message: ConversationMessage) -> Dict[str, Any]:
    """转成接口返回结构，并把 meta 摊平成前端直接可用的字段"""
    meta = message.meta or {}
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "timestamp": message.created_at,
        "metadata": meta,
        # 摊平给前端：历史消息也要能还原工具标签与天气卡片
        "tool_calls": meta.get("tool_calls") or [],
        "weather_info": meta.get("weather_info"),
        "suggested_actions": meta.get("suggested_actions") or [],
        "intent": meta.get("intent"),
    }


async def delete_conversation(db: AsyncSession, user_id: str, conversation_id: str) -> bool:
    """删除会话及其消息

    消息按外键显式删除，而不是依赖 ORM 级联或数据库的 ON DELETE CASCADE：
    - 异步 session 下 ORM 级联要在 flush 期惰性加载子集合，会触发 greenlet 错误；
    - SQLite 默认不强制外键，`ON DELETE CASCADE` 未必生效。
    """
    conversation = await get_conversation(db, user_id, conversation_id)
    if conversation is None:
        return False

    await db.execute(
        delete(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id
        )
    )
    await db.delete(conversation)
    await db.commit()
    logger.info("🗑 删除会话 %s", conversation_id)
    return True


async def load_history_for_agent(
    conversation_id: Optional[str],
    limit: int = 10,
    exclude_message_id: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> List[Dict[str, Any]]:
    """取一段对话历史喂给 Agent（按时间正序）

    `exclude_message_id` 用来排除**本轮刚入库的用户消息**。
    否则它会既出现在历史里、又被当作本轮输入再追加一次，同一句话被送进模型两次。
    """
    if not conversation_id:
        return []

    async with _session(db) as session:
        stmt = select(ConversationMessage).where(
            ConversationMessage.conversation_id == uuid.UUID(str(conversation_id))
        )
        if exclude_message_id:
            try:
                stmt = stmt.where(
                    ConversationMessage.id != uuid.UUID(str(exclude_message_id))
                )
            except (ValueError, AttributeError, TypeError):
                pass
        # 取最近 limit 条：先倒序截断，再翻回正序
        rows = await session.execute(
            stmt.order_by(ConversationMessage.created_at.desc()).limit(limit)
        )
        newest_first = rows.scalars().all()

    return [
        {"role": m.role, "content": m.content}
        for m in reversed(newest_first)
        if (m.content or "").strip()
    ]


async def count_user_messages(conversation_id: str, db: Optional[AsyncSession] = None) -> int:
    """会话里的用户消息条数（供测试与诊断使用）"""
    async with _session(db) as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == uuid.UUID(str(conversation_id)),
                    ConversationMessage.role == "user",
                )
            )
            or 0
        )
