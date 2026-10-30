"""Data access for sessions and messages."""

import re
from uuid import uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import ConversationSession, Message
from app.db.types import utc_now

GENERIC_TITLES = {"conversation": "Conversation", "reflection": "Reflection"}
_LIKE_ESCAPE = "!"
# A bare greeting ("hi", "hey there!", "I'm back") says nothing about the conversation, so it never becomes the
# History title; the next message does.
_GREETING = re.compile(
    r"^\s*((hi|hey|hello|hiya|yo|sup|what'?s up|howdy|good (morning|afternoon|evening)|i'?m back|hi again)"
    r"( there| again| everyone)?[\s,.!?:)]*)+$",
    re.IGNORECASE,
)


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


def _history_filters(user_id: int, session_type: str | None = None, query: str | None = None) -> list:
    """Filters for the user's History: non-empty, not purged, optionally by type and by text."""
    filters = [ConversationSession.user_id == user_id, ConversationSession.transcript_purged_at.is_(None),
               ConversationSession.message_count > 0]
    if session_type:
        filters.append(ConversationSession.type == session_type)
    if query and query.strip():
        # Case-insensitive match on the title or the text of the session's own messages.
        # "%" and "_" typed by the user are matched literally.
        term = query.strip().lower()
        for char in (_LIKE_ESCAPE, "%", "_"):
            term = term.replace(char, _LIKE_ESCAPE + char)
        pattern = f"%{term}%"
        in_messages = (select(Message.id)
                       .where(Message.session_id == ConversationSession.id,
                              func.lower(Message.content).like(pattern, escape=_LIKE_ESCAPE))
                       .exists())
        filters.append(or_(func.lower(ConversationSession.title).like(pattern, escape=_LIKE_ESCAPE), in_messages))
    return filters


def list_sessions(db: Session, user_id: int, limit: int = 50, offset: int = 0, session_type: str | None = None,
                  query: str | None = None) -> list[ConversationSession]:
    """List the user's non-empty sessions, most recently active first."""
    stmt = (
        select(ConversationSession)
        .where(*_history_filters(user_id, session_type, query))
        .order_by(ConversationSession.last_active.desc(), ConversationSession.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def count_sessions(db: Session, user_id: int, session_type: str | None = None, query: str | None = None) -> int:
    stmt = select(func.count(ConversationSession.id)).where(*_history_filters(user_id, session_type, query))
    return db.scalar(stmt) or 0


def export_history(db: Session, user_id: int) -> list[tuple[ConversationSession, list[Message]]]:
    """All of the user's History with its messages, most recently active first."""
    sessions = list(db.scalars(select(ConversationSession).where(*_history_filters(user_id))
                               .order_by(ConversationSession.last_active.desc(), ConversationSession.id)))
    return [(s, get_messages(db, s.id)) for s in sessions]


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


def is_greeting(text: str) -> bool:
    return bool(_GREETING.match(text))


def has_generic_title(conversation: ConversationSession) -> bool:
    return not conversation.title or conversation.title == GENERIC_TITLES.get(conversation.type)


def delete_session(db: Session, conversation: ConversationSession) -> None:
    db.delete(conversation)  # Messages are removed by cascade.
    db.commit()


def delete_all_sessions(db: Session, user_id: int) -> int:
    """Delete every session of the user, with their messages and memory notes. Returns the count."""
    ids = list(db.scalars(select(ConversationSession.id).where(ConversationSession.user_id == user_id)))
    if ids:
        # Explicit message delete: bulk deletes do not run ORM cascades, and SQLite may lack ON DELETE.
        db.execute(delete(Message).where(Message.session_id.in_(ids)))
        db.execute(delete(ConversationSession).where(ConversationSession.id.in_(ids)))
    return len(ids)
