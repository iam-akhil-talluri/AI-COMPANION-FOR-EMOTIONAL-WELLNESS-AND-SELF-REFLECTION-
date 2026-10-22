"""Message handling: validation, rate limiting, reply generation and persistence."""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import ConversationSession
from app.db.types import utc_now
from app.errors import AppError
from app.services import reply_provider
from app.services.conversation_service import (
    GENERIC_TITLES,
    add_message,
    default_title,
    has_generic_title,
    recent_context,
    touch_session,
)
from app.services.event_log import log_event
from app.services.rate_limiter import check_chat_limits

logger = logging.getLogger(__name__)

_REPLY_UNAVAILABLE = "The companion can't reply right now. Please try again in a moment."
_CONVERSATION_LIMIT = "This conversation has reached its length limit. Please start a new conversation."
_RATE_LIMITED = "You're sending messages quickly. Please wait a moment and try again."


@dataclass
class ChatOutcome:
    session_id: str
    response: str
    created_at: datetime = field(default_factory=utc_now)


def validate_text(message: str | None, max_chars: int) -> str:
    text = (message or "").strip()
    if not text:
        raise AppError("empty_message", 422, "Please write a message first.")
    if len(text) > max_chars:
        raise AppError("message_too_long", 422,
                       f"Messages can be up to {max_chars} characters. Try splitting it into smaller parts.")
    return text


def send_message(db: Session, conversation: ConversationSession, message: str,
                 settings: Settings | None = None) -> ChatOutcome:
    settings = settings or get_settings()
    session_id = conversation.id

    text = validate_text(message, settings.max_message_chars)
    if (conversation.message_count or 0) + 2 > settings.max_messages_per_session:
        raise AppError("conversation_limit", 429, _CONVERSATION_LIMIT)

    if not check_chat_limits(f"user:{conversation.user_id}", settings.rate_limit_per_minute,
                             settings.rate_limit_per_hour):
        log_event(db, "rate_limit_triggered", session_id, "warning")
        db.commit()
        raise AppError("rate_limited", 429, _RATE_LIMITED, headers={"Retry-After": "60"})

    log_event(db, "chat_request", session_id)

    context = recent_context(db, session_id, settings.context_messages)

    # Fail closed: nothing is stored without a reply.
    try:
        reply = reply_provider.generate_reply(context, text)
    except reply_provider.ReplyUnavailableError as exc:
        log_event(db, "api_error", session_id, "error", f"reply_unavailable: {exc}")
        db.commit()
        raise AppError("reply_unavailable", 503, _REPLY_UNAVAILABLE) from None

    if settings.store_transcripts:
        add_message(db, session_id, "user", text)
        add_message(db, session_id, "assistant", reply)
        if has_generic_title(conversation):
            conversation.title = default_title(text)
    if not conversation.title:
        conversation.title = GENERIC_TITLES.get(conversation.type, "Conversation")
    touch_session(conversation, added=2)
    log_event(db, "response_generated", session_id)
    db.commit()

    return ChatOutcome(session_id=session_id, response=reply)
