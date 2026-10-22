"""Data access for sessions and messages."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ConversationSession, Message
from app.db.types import utc_now

GENERIC_TITLES = {"conversation": "Conversation", "reflection": "Reflection"}


def create_session(db: Session, user_id: int, session_type: str = "conversation", title: str | None = None,
                   prompt: str | None = None) -> ConversationSession:
    conversation = ConversationSession(id=str(uuid4()), user_id=user_id, type=session_type,
                                       title=title, prompt=prompt)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_owned_session(db: Session, session_id: str, user_id: int) -> ConversationSession | None:
    """Return the session if it belongs to the user, otherwise None."""
    conversation = db.get(ConversationSession, session_id)
    if conversation is None or conversation.user_id != user_id:
        return None
    return conversation


def list_sessions(db: Session, user_id: int, limit: int = 50, offset: int = 0) -> list[ConversationSession]:
    """List the user's non-empty sessions, most recently active first."""
    stmt = (
        select(ConversationSession)
        .where(ConversationSession.user_id == user_id, ConversationSession.transcript_purged_at.is_(None),
               ConversationSession.message_count > 0)
        .order_by(ConversationSession.last_active.desc(), ConversationSession.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def get_messages(db: Session, session_id: str) -> list[Message]:
    stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at, Message.id)
    return list(db.scalars(stmt))


def recent_context(db: Session, session_id: str, limit: int) -> list[dict]:
    """Return the last `limit` messages of a session, oldest first."""
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return [{"role": m.role, "content": m.content} for m in reversed(list(db.scalars(stmt)))]


def add_message(db: Session, session_id: str, role: str, content: str) -> Message:
    message = Message(session_id=session_id, role=role, content=content)
    db.add(message)
    return message


def touch_session(conversation: ConversationSession, added: int = 0) -> None:
    """Update the session's activity time and message count.

    The count is incremented in SQL so concurrent requests do not overwrite each other.
    """
    conversation.last_active = utc_now()
    if added:
        conversation.message_count = ConversationSession.message_count + added


def default_title(text: str, max_words: int = 6, max_chars: int = 160) -> str:
    words = text.split()
    title = " ".join(words[:max_words])
    if len(words) > max_words:
        title += "..."
    return title[:max_chars]


def has_generic_title(conversation: ConversationSession) -> bool:
    return not conversation.title or conversation.title == GENERIC_TITLES.get(conversation.type)


def delete_session(db: Session, conversation: ConversationSession) -> None:
    db.delete(conversation)  # Messages are removed by cascade.
    db.commit()
