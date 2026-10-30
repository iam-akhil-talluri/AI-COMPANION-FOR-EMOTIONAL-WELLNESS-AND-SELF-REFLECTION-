"""Private journal entries (Coping Tools > Journaling).

    entry
     -> validate (empty, MAX_JOURNAL_CHARS) and rate limit (JOURNAL_ENTRIES_PER_HOUR)
     -> safety check (rules + OpenAI Moderation); no AI ever reads or answers a journal entry
     -> saved; elevated risk returns support resources, high risk returns crisis resources
        (the frontend opens the Support & Crisis Resources screen)

The entry is always saved: it is the user's own writing and nothing is generated from it.
If Moderation is unavailable the rules still screen it (there is no AI call to protect).
Escalations are recorded as anonymized safety events (no text, no user ID); logs never
contain the text. Entries are deleted with the account, by the user, or by the retention job.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.content import resources_for
from app.db.models import JournalEntry, SafetyEvent, User
from app.errors import AppError
from app.services import ai_service
from app.services.ai_service import AIServiceError
from app.services.chat_service import validate_text
from app.services.companion import resource_kind
from app.services.event_log import log_event
from app.services.rate_limiter import limiter
from app.services.safety_service import SafetyResult, SafetyServiceError, check_message, classify_with_rules

logger = logging.getLogger(__name__)

JOURNAL_ACTIONS = {"crisis": "journal_crisis_resources", "support": "journal_support_resources"}
_RATE_LIMITED = "You've saved a lot of journal entries recently. Please try again a little later."
_DISABLED = "Journal entries can't be saved on this server."


@dataclass
class JournalOutcome:
    entry: JournalEntry
    status: str = "ok"  # ok | support | crisis
    risk_level: str = "low"
    resources: list[dict] = field(default_factory=list)


def _screen(text: str, settings: Settings) -> SafetyResult:
    """Rules + Moderation. Without Moderation the rules alone screen it: no AI sees the entry."""
    try:
        return check_message(text, ai_service.moderation_client(settings))
    except (SafetyServiceError, AIServiceError) as exc:
        logger.warning("Journal safety check: moderation unavailable (%s); rules only", type(exc).__name__)
        return classify_with_rules(text)


def create_entry(db: Session, user: User, content: str, prompt: str | None = None,
                 settings: Settings | None = None) -> JournalOutcome:
    settings = settings or get_settings()
    if not settings.store_transcripts:
        raise AppError("journal_disabled", 403, _DISABLED)
    text = validate_text(content, settings.max_journal_chars)
    if not limiter.allow(f"journal:user:{user.id}", settings.journal_entries_per_hour, 3600):
        log_event(db, "rate_limit_triggered", level="warning", detail="journal")
        db.commit()
        raise AppError("rate_limited", 429, _RATE_LIMITED, headers={"Retry-After": "3600"})

    safety = _screen(text, settings)
    entry = JournalEntry(user_id=user.id, prompt=(prompt or "").strip()[:300] or None, content=text)
    db.add(entry)

    status, resources = "ok", []
    if safety.escalated:
        status = "crisis" if safety.risk_level == "high" else "support"
        resources = resources_for(resource_kind(safety))
        category = safety.primary_category or "unknown"
        db.add(SafetyEvent(stage="input", risk_level=safety.risk_level, category=category,
                           action=JOURNAL_ACTIONS[status], source=safety.source))
        log_event(db, "escalation_triggered", level="warning",
                  detail=f"risk={safety.risk_level} category={category} action={JOURNAL_ACTIONS[status]}")
    log_event(db, "journal_saved", detail=f"risk={safety.risk_level}")
    db.commit()
    db.refresh(entry)
    return JournalOutcome(entry=entry, status=status, risk_level=safety.risk_level, resources=resources)


def list_entries(db: Session, user_id: int, limit: int = 20, offset: int = 0) -> list[JournalEntry]:
    stmt = (select(JournalEntry).where(JournalEntry.user_id == user_id)
            .order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc()).limit(limit).offset(offset))
    return list(db.scalars(stmt))


def count_entries(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.user_id == user_id)) or 0


def delete_entry(db: Session, user_id: int, entry_id: int) -> None:
    """Delete the user's entry. Unknown and other users' entries are both 404."""
    entry = db.get(JournalEntry, entry_id)
    if entry is None or entry.user_id != user_id:
        raise AppError("not_found", 404, "Journal entry not found.")
    db.delete(entry)
    log_event(db, "journal_deleted")
    db.commit()
