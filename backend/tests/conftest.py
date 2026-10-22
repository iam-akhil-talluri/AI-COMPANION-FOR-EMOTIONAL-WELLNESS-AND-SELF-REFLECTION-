"""Pytest fixtures.

Each test uses a fresh in-memory SQLite database. Set TEST_DATABASE_URL to run against an
empty MySQL database instead; its tables are dropped and recreated for every test.
"""

import os
from collections.abc import Generator
from unittest.mock import MagicMock, patch

# Must be set before the app is imported.
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": "sqlite://",
    "JWT_SECRET": "test-jwt-secret-that-is-long-enough-for-hs256-signing",
    "RATE_LIMIT_PER_MINUTE": "1000",
    "RATE_LIMIT_PER_HOUR": "1000",
    "RETENTION_INTERVAL_HOURS": "0",
    "CORS_ORIGINS": "http://localhost:5173",
    # Tests never call OpenAI, even when backend/.env holds a real key.
    "OPENAI_API_KEY": "",
    "USE_OPENAI_MODERATION": "false",
    "AI_MONTHLY_BUDGET_USD": "",
})

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.models import Base
from app.db.session import build_engine, get_db
from app.main import app
from app.services import ai_service, reply_provider
from app.services.companion import companion_reply
from app.services.rate_limiter import limiter
from app.services.user_service import create_user
from tests.helpers import MOCK_REPLY, PASSWORD, completion, moderation_result, register


def _sqlite_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.fixture(autouse=True)
def _reset_shared_state():
    limiter.reset()
    reply_provider.set_reply_provider(None)
    yield
    limiter.reset()
    reply_provider.set_reply_provider(None)


@pytest.fixture
def engine():
    url = os.environ.get("TEST_DATABASE_URL")
    engine = build_engine(url) if url else _sqlite_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    if url:
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        yield db


@pytest.fixture
def session_factory(engine):
    """Session factory for code that opens its own sessions."""
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with patch("app.services.retention.get_sessionmaker", return_value=factory), \
            patch("scripts.create_admin.get_sessionmaker", return_value=factory):
        yield factory


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def fake_replies() -> MagicMock:
    """Register a simple (context, message) mock reply provider that returns MOCK_REPLY."""
    def simple_provider(context, message): ...

    provider = MagicMock(spec=simple_provider, return_value=MOCK_REPLY)
    reply_provider.set_reply_provider(provider)
    return provider


@pytest.fixture
def openai(monkeypatch) -> MagicMock:
    """Register the real companion with a mocked OpenAI client (AI configured, moderation off)."""
    fake = MagicMock()
    fake.chat.completions.create.return_value = completion()
    fake.moderations.create.return_value = moderation_result()
    monkeypatch.setattr(ai_service, "get_client", lambda settings=None: fake)
    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")
    reply_provider.set_reply_provider(companion_reply)
    return fake


@pytest.fixture
def auth(client) -> dict:
    return register(client)


@pytest.fixture
def admin_auth(client, db_session) -> dict:
    create_user(db_session, "site-admin", PASSWORD, role="admin")
    response = client.post("/api/auth/login", json={"username": "site-admin", "password": PASSWORD, "admin": True})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}
