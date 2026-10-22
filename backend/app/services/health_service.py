"""Service health checks."""

from datetime import timedelta

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Base, Interaction
from app.db.session import check_db
from app.db.types import utc_now

# How far back a failed safety check or AI request marks the service as degraded.
RECENT_FAILURE_WINDOW = timedelta(minutes=15)


def missing_tables(db: Session) -> list[str]:
    """Return application tables missing from the database."""
    try:
        existing = set(inspect(db.connection()).get_table_names())
    except Exception:
        return sorted(Base.metadata.tables)
    return sorted(set(Base.metadata.tables) - existing)


def _latest_status(db: Session, *, used_ai: bool | None = None) -> str | None:
    """Status of the most recent interaction in the window (optionally only AI attempts)."""
    stmt = select(Interaction.status).where(Interaction.created_at >= utc_now() - RECENT_FAILURE_WINDOW)
    if used_ai is not None:
        stmt = stmt.where((Interaction.used_ai == used_ai) | (Interaction.status == "ai_error"))
    return db.scalar(stmt.order_by(Interaction.created_at.desc(), Interaction.id.desc()).limit(1))


def safety_and_ai_health(db: Session, settings: Settings, schema_ok: bool) -> list[dict]:
    """Health of the safety layer and the AI service, judged from recent requests.

    It does not call OpenAI, so the health check stays free and fast.
    """
    safety = "Healthy"
    ai = "Healthy" if settings.ai_configured else "Not configured"
    if schema_ok:
        if _latest_status(db) == "safety_error":
            safety = "Degraded"
        if settings.ai_configured and _latest_status(db, used_ai=True) == "ai_error":
            ai = "Degraded"
    mode = "rules + OpenAI Moderation" if settings.moderation_enabled else "rules only"
    return [
        {"name": "Safety / Moderation", "status": safety, "detail": mode},
        {"name": "AI Service", "status": ai, "detail": settings.openai_model if settings.ai_configured else None},
    ]


def service_health(db: Session, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    db_ok = check_db(db)
    # A reachable database without the schema is not ready.
    schema_ok = db_ok and not missing_tables(db)
    if not db_ok:
        db_status = "Unavailable"
    elif not schema_ok:
        db_status = "Not migrated"
    else:
        db_status = "Healthy"
    services = [
        {"name": "Backend / API", "status": "Healthy"},
        {"name": "Database", "status": db_status},
        {"name": "Logging", "status": "Healthy" if schema_ok else "Unavailable"},
        *safety_and_ai_health(db, settings, schema_ok),
    ]
    # Readiness depends on the database only: crisis support works without the AI.
    return {"status": "healthy" if schema_ok else "unhealthy", "environment": settings.environment,
            "services": services}
