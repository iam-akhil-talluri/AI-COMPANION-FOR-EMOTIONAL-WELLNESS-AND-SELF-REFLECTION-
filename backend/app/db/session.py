"""Database engine and session management."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def normalize_database_url(database_url: str) -> str:
    """Normalize MySQL URLs to the PyMySQL driver and the utf8mb4 charset."""
    url = make_url(database_url)
    if url.get_backend_name() == "mysql":
        if url.drivername == "mysql":
            url = url.set(drivername="mysql+pymysql")
        if "charset" not in url.query:
            url = url.update_query_dict({"charset": "utf8mb4"})
    return url.render_as_string(hide_password=False)


def build_engine(database_url: str) -> Engine:
    url = normalize_database_url(database_url)
    backend = make_url(url).get_backend_name()
    if backend == "sqlite":
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _):  # SQLite enforces foreign keys only when enabled
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    # Recycle connections before the server's idle timeout.
    return create_engine(url, pool_pre_ping=True, pool_recycle=280, pool_size=5, max_overflow=10)


@lru_cache
def get_engine() -> Engine:
    return build_engine(get_settings().database_url)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a session per request, rolling back on error."""
    db = get_sessionmaker()()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_db(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
