"""Data retention.

Deletes transcript text older than RETENTION_DAYS and empty sessions older than
EMPTY_SESSION_GRACE. Session metadata is kept.
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import ConversationSession, Message
from app.db.session import get_sessionmaker
from app.db.types import utc_now
from app.services.event_log import log_event

logger = logging.getLogger(__name__)

_BATCH = 500
# Empty sessions younger than this may still be in use.
EMPTY_SESSION_GRACE = timedelta(days=1)


def purge_expired(db: Session, retention_days: int) -> int:
    """Delete expired transcripts and stale empty sessions. Return the number of rows removed."""
    if retention_days <= 0:
        return 0
    now = utc_now()
    cutoff = now - timedelta(days=retention_days)
    empty = db.execute(
        delete(ConversationSession)
        .where(ConversationSession.message_count == 0, ConversationSession.last_active < now - EMPTY_SESSION_GRACE)
    ).rowcount or 0
    expired = list(db.scalars(
        select(ConversationSession.id)
        .where(ConversationSession.last_active < cutoff, ConversationSession.transcript_purged_at.is_(None))
    ))
    removed = 0
    for start in range(0, len(expired), _BATCH):
        batch = expired[start:start + _BATCH]
        removed += db.execute(delete(Message).where(Message.session_id.in_(batch))).rowcount or 0
        db.execute(update(ConversationSession).where(ConversationSession.id.in_(batch))
                   .values(transcript_purged_at=now))
    if removed or expired or empty:
        log_event(db, "retention_purge", detail=f"rows={removed} sessions={len(expired)} empty_sessions={empty}")
    db.commit()
    return removed + empty


def _purge_once(retention_days: int) -> None:
    with get_sessionmaker()() as db:
        removed = purge_expired(db, retention_days)
    if removed:
        logger.info("Retention: removed %s expired rows", removed)


async def retention_loop(settings: Settings) -> None:
    """Run the purge at startup and then every RETENTION_INTERVAL_HOURS. The purge is idempotent."""
    interval = settings.retention_interval_hours * 3600
    while True:
        try:
            await asyncio.to_thread(_purge_once, settings.retention_days)
        except Exception:
            logger.exception("Retention purge failed; will retry at the next interval")
        await asyncio.sleep(interval)
