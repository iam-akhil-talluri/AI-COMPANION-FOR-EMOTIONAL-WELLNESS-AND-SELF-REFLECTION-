"""Operational event logging.

Records event metadata only, never message text. The caller commits.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import EventLog

logger = logging.getLogger("app.events")

EVENT_TYPES = {
    "chat_request",
    "response_generated",
    "api_error",
    "rate_limit_triggered",
    "user_registered",
    "user_login",
    "admin_login",
    "login_failed",
    "retention_purge",
    "safety_check",
    "risk_detected",
    "escalation_triggered",
    "response_blocked",
    "safety_unavailable",
}

_LEVELS = {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}

# Display labels for the admin log view, as (type, message).
_LOG_LABELS = {
    "chat_request": ("Session", "Message received"),
    "response_generated": ("Session", "Reply saved"),
    "api_error": ("Error", "Service request failed"),
    "rate_limit_triggered": ("System", "Rate limit reached"),
    "user_registered": ("Account", "New account created"),
    "user_login": ("Account", "User signed in"),
    "admin_login": ("Account", "Administrator signed in"),
    "login_failed": ("Account", "Sign-in attempt failed"),
    "retention_purge": ("System", "Expired transcripts removed"),
    "safety_check": ("Safety Check", "Safety check completed"),
    "risk_detected": ("Safety", "Sensitive topic answered with a boundary"),
    "escalation_triggered": ("Safety", "Safety concern routed to support resources"),
    "response_blocked": ("Safety", "AI reply blocked by the output check"),
    "safety_unavailable": ("Error", "Safety check failed; message not sent"),
}
_STATUS = {"info": "OK", "warning": "Warning", "error": "Error"}


def log_event(
    db: Session,
    event_type: str,
    session_id: str | None = None,
    level: str = "info",
    detail: str | None = None,
) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    if level not in _LEVELS:
        raise ValueError(f"unknown level: {level}")
    db.add(
        EventLog(
            event_type=event_type,
            session_id=session_id,
            level=level,
            detail=(detail or "")[:200] or None,
            environment=get_settings().environment,
        )
    )
    logger.log(_LEVELS[level], "event=%s session=%s detail=%s", event_type, session_id, detail)


def recent_logs(db: Session, limit: int = 50) -> list[dict]:
    rows = db.scalars(select(EventLog).order_by(EventLog.created_at.desc(), EventLog.id.desc()).limit(limit))
    out = []
    for row in rows:
        kind, message = _LOG_LABELS.get(row.event_type, ("System", row.event_type))
        out.append({"time": row.created_at, "type": kind, "event": row.event_type, "message": message,
                    "status": _STATUS.get(row.level, "OK"), "environment": row.environment})
    return out
