"""Cross-session memory: one short, safety-checked note per session.

    session goes quiet (MEMORY_IDLE_MINUTES), or the user starts a new session
     -> skip: memory off (global or user), transcripts not stored, AI not configured or over budget,
              too few messages, or the session had a high-risk message (crisis sessions are never remembered)
     -> AI writes a note of at most 60 words (content/summary_prompt.md)
     -> the note must pass the output check and the input safety check (risk below elevated)
     -> stored on the session; the newest notes from a user's OTHER sessions go with each reply

The note text is never logged; only the outcome. A failure (AI or moderation down) leaves the
session pending, so the next run tries again. Users can turn memory off and view or delete notes.
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.content import summary_prompt
from app.db.models import ConversationSession, Interaction, Message, SafetyEvent, User
from app.db.session import get_sessionmaker
from app.db.types import utc_now

# chat_service imports this module, so it is imported as a module (used at call time).
from app.services import ai_service, chat_service
from app.services.ai_service import AIServiceError, estimate_cost
from app.services.event_log import log_event
from app.services.safety_service import RISK_ORDER, SafetyServiceError, check_message, check_output, sanitize_output

logger = logging.getLogger(__name__)

# Messages read when writing a note; older ones in a long session are left out.
SUMMARY_SOURCE_MESSAGES = 40
MAX_NOTE_CHARS = 500
NO_NOTE = "NONE"
_SPEAKERS = {"user": "User", "assistant": "Companion"}


def memory_active(user: User, settings: Settings) -> bool:
    return settings.memory_enabled and settings.store_transcripts and user.memory_enabled


def _had_high_risk(db: Session, session_id: str) -> bool:
    stmt = select(SafetyEvent.id).where(SafetyEvent.session_id == session_id,
                                        SafetyEvent.risk_level == "high").limit(1)
    return db.scalar(stmt) is not None


def _source_messages(db: Session, session_id: str) -> list[Message]:
    stmt = (select(Message).where(Message.session_id == session_id)
            .order_by(Message.created_at.desc(), Message.id.desc()).limit(SUMMARY_SOURCE_MESSAGES))
    return list(reversed(list(db.scalars(stmt))))


def _summary_request(messages: list[Message]) -> list[dict[str, str]]:
    # The transcript is data for the summarizer, inside delimiters, never instructions.
    lines = "\n".join(f"{_SPEAKERS.get(m.role, 'User')}: {m.content}" for m in messages)
    return [
        {"role": "system", "content": summary_prompt()},
        {"role": "user", "content": f"<conversation>\n{lines}\n</conversation>"},
    ]


def _note_is_safe(note: str, settings: Settings) -> bool:
    """A note must pass the output check and must not itself read as an elevated or high risk message.

    Raises SafetyServiceError or AIServiceError when moderation can't run (the caller retries later).
    """
    client = ai_service.moderation_client(settings)
    if not check_output(note, client).safe:
        return False
    return RISK_ORDER[check_message(note, client).risk_level] < RISK_ORDER["elevated"]


def _finish(conversation: ConversationSession, note: str | None) -> None:
    conversation.summary = note
    conversation.summary_updated_at = utc_now()
    conversation.summarized_count = conversation.message_count or 0


def summarize_session(db: Session, conversation: ConversationSession, settings: Settings | None = None) -> str | None:
    """Write (or clear) the session's note and return it. Never raises; failures are retried on a later run."""
    settings = settings or get_settings()
    session_id = conversation.id
    user = conversation.user
    if not memory_active(user, settings) or not settings.ai_configured or conversation.transcript_purged_at:
        return None
    if (conversation.message_count or 0) < settings.memory_min_messages:
        return None
    if chat_service.budget_exhausted(db, settings):
        return None

    if _had_high_risk(db, session_id):
        _finish(conversation, None)
        log_event(db, "memory_summary_skipped", session_id, detail="reason=high_risk")
        db.commit()
        return None

    try:
        result = ai_service.generate(_summary_request(_source_messages(db, session_id)), settings,
                                     max_tokens=settings.memory_summary_max_tokens)
        text = result.text.strip()
        safe = text.upper().rstrip(".") != NO_NOTE and _note_is_safe(text, settings)
    except (AIServiceError, SafetyServiceError) as exc:
        logger.warning("Memory note for a session could not be written: %s", getattr(exc, "reason", type(exc).__name__))
        db.rollback()
        return None

    note = sanitize_output(text, MAX_NOTE_CHARS) if safe else None
    _finish(conversation, note)
    db.add(Interaction(
        session_id=session_id, purpose="summary", safety_checked=True, status="ok" if safe else "blocked",
        used_ai=True, model=result.model, prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        estimated_cost_usd=estimate_cost(result.prompt_tokens, result.completion_tokens, settings),
        latency_ms=result.latency_ms,
    ))
    if note:
        log_event(db, "memory_summarized", session_id, detail=f"tokens={result.completion_tokens}")
    else:
        reason = "nothing_to_remember" if text.upper().rstrip(".") == NO_NOTE else "failed_safety_check"
        log_event(db, "memory_summary_skipped", session_id, detail=f"reason={reason}")
    db.commit()
    return note


def pending_sessions(db: Session, settings: Settings, user_id: int | None = None,
                     idle: timedelta | None = None, exclude_session_id: str | None = None) -> list[ConversationSession]:
    """Sessions with new messages since their last note that have been quiet for `idle`."""
    idle = timedelta(minutes=settings.memory_idle_minutes) if idle is None else idle
    stmt = (
        select(ConversationSession).join(User, User.id == ConversationSession.user_id)
        .where(User.memory_enabled.is_(True), ConversationSession.transcript_purged_at.is_(None),
               ConversationSession.message_count >= settings.memory_min_messages,
               ConversationSession.message_count > ConversationSession.summarized_count,
               ConversationSession.last_active <= utc_now() - idle)
        .order_by(ConversationSession.last_active)
        .limit(200)
    )
    if user_id is not None:
        stmt = stmt.where(ConversationSession.user_id == user_id)
    if exclude_session_id is not None:
        stmt = stmt.where(ConversationSession.id != exclude_session_id)
    return list(db.scalars(stmt))


def summarize_pending(db: Session, settings: Settings | None = None, **filters) -> int:
    """Write notes for every pending session. Returns the number of notes written."""
    settings = settings or get_settings()
    if not (settings.memory_enabled and settings.store_transcripts and settings.ai_configured):
        return 0
    return sum(1 for conversation in pending_sessions(db, settings, **filters)
               if summarize_session(db, conversation, settings))


def summarize_user_sessions(user_id: int, exclude_session_id: str) -> None:
    """Background task when a user starts a new session: their earlier sessions are finished, so
    they are summarized now instead of after the idle time. Runs after the response is sent."""
    settings = get_settings()
    if not (settings.memory_enabled and settings.store_transcripts and settings.ai_configured):
        return
    try:
        with get_sessionmaker()() as db:
            summarize_pending(db, settings, user_id=user_id, idle=timedelta(0),
                              exclude_session_id=exclude_session_id)
    except Exception:
        logger.exception("Memory notes for a new session's earlier sessions failed; the background job will retry")


def memory_notes(db: Session, user_id: int, exclude_session_id: str | None = None,
                 limit: int | None = None) -> list[ConversationSession]:
    """The user's sessions that have a note, most recently active first."""
    stmt = (
        select(ConversationSession)
        .where(ConversationSession.user_id == user_id, ConversationSession.summary.is_not(None),
               ConversationSession.transcript_purged_at.is_(None))
        .order_by(ConversationSession.last_active.desc(), ConversationSession.id)
    )
    if exclude_session_id is not None:
        stmt = stmt.where(ConversationSession.id != exclude_session_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def memory_for_reply(db: Session, user: User, session_id: str, settings: Settings) -> tuple[str, ...]:
    """The notes sent with a reply: the newest MEMORY_SESSIONS from the user's other sessions."""
    if not memory_active(user, settings):
        return ()
    return tuple(s.summary for s in memory_notes(db, user.id, session_id, settings.memory_sessions))


def clear_notes(db: Session, user_id: int, session_id: str | None = None) -> int:
    """Delete the user's notes (or one session's note). Transcripts are kept.

    The session is marked as summarized up to now, so the note is not written again unless
    the user adds new messages to that session.
    """
    stmt = update(ConversationSession).where(ConversationSession.user_id == user_id)
    if session_id is not None:
        stmt = stmt.where(ConversationSession.id == session_id)
    cleared = db.execute(stmt.values(summary=None, summary_updated_at=None,
                                     summarized_count=ConversationSession.message_count)).rowcount or 0
    log_event(db, "memory_cleared", session_id, detail=f"sessions={cleared}")
    db.commit()
    return cleared


def set_memory_enabled(db: Session, user: User, enabled: bool) -> None:
    """Turn memory on or off for the user. Turning it off also deletes their notes."""
    user.memory_enabled = enabled
    log_event(db, "memory_setting_changed", detail=f"enabled={str(enabled).lower()}")
    if not enabled:
        clear_notes(db, user.id)  # commits
    else:
        db.commit()


def _summarize_once(settings: Settings) -> None:
    with get_sessionmaker()() as db:
        written = summarize_pending(db, settings)
    if written:
        logger.info("Memory: wrote %s session notes", written)


async def memory_loop(settings: Settings) -> None:
    """Summarize quiet sessions every MEMORY_INTERVAL_MINUTES."""
    interval = settings.memory_interval_minutes * 60
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(_summarize_once, settings)
        except Exception:
            logger.exception("Memory job failed; will retry at the next interval")
