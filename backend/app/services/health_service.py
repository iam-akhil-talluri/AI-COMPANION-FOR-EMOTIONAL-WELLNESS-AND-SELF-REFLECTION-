"""Service health checks."""

import logging
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Base, Interaction
from app.db.session import check_db
from app.db.types import utc_now

logger = logging.getLogger(__name__)

# How far back a failed safety check or AI request marks the service as degraded.
RECENT_FAILURE_WINDOW = timedelta(minutes=15)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def missing_tables(db: Session) -> list[str]:
    """Return application tables missing from the database."""
    try:
        existing = set(inspect(db.connection()).get_table_names())
    except Exception:
        return sorted(Base.metadata.tables)
    return sorted(set(Base.metadata.tables) - existing)


@lru_cache
def head_revision() -> str | None:
    """The newest migration in migrations/, or None when the folder isn't there."""
    if not MIGRATIONS_DIR.is_dir():
        return None
    # Alembic announces each of its plugins at INFO when it loads; that is noise in the app log.
    logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config).get_current_head()


def database_revision(db: Session) -> str | None:
    """The migration the database is at, or None for a database Alembic never touched."""
    try:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        db.rollback()
        return None


def outdated_schema(db: Session) -> tuple[str, str] | None:
    """(database revision, code revision) when the database is behind the code, else None.

    A migration can add only columns (0003 did), which the missing-table check can't see.
    Databases created without Alembic (tests) have no version and are judged by their tables.
    """
    current, head = database_revision(db), head_revision()
    if current is None or head is None or current == head:
        return None
    return current, head


def log_schema_problems(db: Session) -> None:
    """At startup: say clearly when the database needs `alembic upgrade head`."""
    try:
        outdated = outdated_schema(db)
        missing = missing_tables(db)
    except Exception:
        logger.exception("Could not check the database schema")
        return
    if outdated:
        logger.error("The database is at migration %s but the code needs %s. Run `python -m alembic upgrade head` "
                     "in backend/ before using the app.", *outdated)
    elif missing:
        logger.error("The database is missing tables (%s). Run `python -m alembic upgrade head` in backend/.",
                     ", ".join(missing))


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
    # A reachable database without the schema, or behind the code's migrations, is not ready.
    schema_ok = db_ok and not missing_tables(db) and outdated_schema(db) is None
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
