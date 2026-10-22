"""Service health checks."""

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Base
from app.db.session import check_db


def missing_tables(db: Session) -> list[str]:
    """Return application tables missing from the database."""
    try:
        existing = set(inspect(db.connection()).get_table_names())
    except Exception:
        return sorted(Base.metadata.tables)
    return sorted(set(Base.metadata.tables) - existing)


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
    ]
    return {"status": "healthy" if schema_ok else "unhealthy", "environment": settings.environment,
            "services": services}
