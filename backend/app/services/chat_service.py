"""Message handling: validation, rate limiting, reply generation and persistence.

Replies come from the registered reply provider (the companion: safety check, escalation,
AI reply and output check). This module stores the messages and the anonymized safety and
usage metrics, and maps provider failures to API errors. Nothing is stored without a reply.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import ConversationSession, Interaction, SafetyEvent
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
from app.services.reply_provider import Reply, ReplyContext

logger = logging.getLogger(__name__)

_REPLY_UNAVAILABLE = "The companion can't reply right now. Please try again in a moment."
_SAFETY_UNAVAILABLE = ("We couldn't complete the safety check on your message, so it wasn't sent. Please try again "
                       "in a moment. If you need support right now, you can call or text 988 at any time.")
_CONVERSATION_LIMIT = "This conversation has reached its length limit. Please start a new conversation."
_RATE_LIMITED = "You're sending messages quickly. Please wait a moment and try again."

# An escalated message this recent keeps the AI aware that the user may be at risk.
PRIOR_RISK_WINDOW = timedelta(hours=24)


@dataclass
class ChatOutcome:
    session_id: str
    response: str
    status: str = "ok"
    risk_level: str | None = None
    resources: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)


def validate_text(message: str | None, max_chars: int) -> str:
    text = (message or "").strip()
    if not text:
        raise AppError("empty_message", 422, "Please write a message first.")
    if len(text) > max_chars:
        raise AppError("message_too_long", 422,
                       f"Messages can be up to {max_chars} characters. Try splitting it into smaller parts.")
    return text


def had_prior_risk(db: Session, session_id: str) -> bool:
    stmt = select(SafetyEvent.id).where(
        SafetyEvent.session_id == session_id, SafetyEvent.stage == "input",
        SafetyEvent.risk_level.in_(("elevated", "high")), SafetyEvent.created_at >= utc_now() - PRIOR_RISK_WINDOW,
    ).limit(1)
    return db.scalar(stmt) is not None


def month_to_date_cost(db: Session) -> float:
    start = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.scalar(select(func.sum(Interaction.estimated_cost_usd)).where(Interaction.created_at >= start))
    return float(total or 0)


def budget_exhausted(db: Session, settings: Settings) -> bool:
    budget = settings.ai_monthly_budget_usd
    return budget is not None and month_to_date_cost(db) >= budget


def _record_reply(db: Session, session_id: str, reply: Reply) -> None:
    """Store the anonymized metrics and log events for a reply. No message text."""
    for event in reply.safety_events:
        db.add(SafetyEvent(session_id=session_id, stage=event.stage, risk_level=event.risk_level,
                           category=event.category, action=event.action, source=event.source))
    usage = reply.usage
    db.add(Interaction(session_id=session_id, safety_checked=reply.safety_checked, risk_level=reply.risk_level,
                       status=reply.outcome, used_ai=reply.used_ai, model=usage.model,
                       prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
                       estimated_cost_usd=usage.estimated_cost_usd, latency_ms=usage.latency_ms))

    if reply.safety_checked:
        log_event(db, "safety_check", session_id, detail=f"risk={reply.risk_level}")
    for event in reply.safety_events:
        detail = f"risk={event.risk_level} category={event.category} action={event.action} source={event.source}"
        if event.stage == "output":
            log_event(db, "response_blocked", session_id, "warning", detail)
        elif event.action.endswith("_template") or event.action == "ai_with_support_note":
            log_event(db, "escalation_triggered", session_id, "warning", detail)
        else:
            log_event(db, "risk_detected", session_id, detail=detail)
    log_event(db, "response_generated", session_id,
              detail=f"status={reply.status} ai={reply.used_ai} tokens={usage.completion_tokens}")


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
    info = ReplyContext(
        session_id=session_id,
        session_type=conversation.type,
        session_prompt=conversation.prompt,
        message_count=conversation.message_count or 0,
        prior_risk=had_prior_risk(db, session_id),
        ai_budget_exhausted=budget_exhausted(db, settings),
    )

    # Fail closed: nothing is stored without a reply.
    try:
        reply = reply_provider.generate_reply(context, text, info)
    except reply_provider.SafetyUnavailableError as exc:
        log_event(db, "safety_unavailable", session_id, "error", exc.reason)
        db.add(Interaction(session_id=session_id, safety_checked=False, status="safety_error"))
        db.commit()
        raise AppError("safety_unavailable", 503, _SAFETY_UNAVAILABLE) from None
    except reply_provider.ReplyUnavailableError as exc:
        log_event(db, "api_error", session_id, "error", f"reply_unavailable: {exc.reason}")
        db.add(Interaction(session_id=session_id, safety_checked=exc.risk_level is not None,
                           risk_level=exc.risk_level, status="ai_error"))
        db.commit()
        raise AppError("reply_unavailable", 503, _REPLY_UNAVAILABLE) from None

    if settings.store_transcripts:
        add_message(db, session_id, "user", text)
        add_message(db, session_id, "assistant", reply.text)
        # A message that was escalated never becomes the visible session title.
        if has_generic_title(conversation) and reply.status == "ok":
            conversation.title = default_title(text)
    if not conversation.title:
        conversation.title = GENERIC_TITLES.get(conversation.type, "Conversation")
    touch_session(conversation, added=2)
    _record_reply(db, session_id, reply)
    db.commit()

    return ChatOutcome(session_id=session_id, response=reply.text, status=reply.status,
                       risk_level=reply.risk_level, resources=reply.resources)
