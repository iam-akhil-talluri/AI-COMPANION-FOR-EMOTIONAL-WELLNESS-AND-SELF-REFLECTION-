"""Health, HTTP hardening, error format and configuration."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.db.session import get_db
from app.main import app, create_app
from tests.helpers import ORIGIN, new_session


def test_health_reports_services_without_secrets(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy" and body["environment"] == "test"
    assert {s["name"]: s["status"] for s in body["services"]}["Database"] == "Healthy"
    assert "jwt" not in response.text.lower()
    assert client.get("/health").status_code == 200


def test_health_is_503_when_the_database_is_down(client):
    with patch("app.services.health_service.check_db", return_value=False):
        response = client.get("/health")
    assert response.status_code == 503 and response.json()["status"] == "unhealthy"


def test_health_is_503_when_migrations_have_not_run():
    """A reachable database without the schema is not ready."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.services.health_service import service_health

    engine = create_engine("sqlite://")
    with Session(engine) as empty_db:
        body = service_health(empty_db)
    engine.dispose()
    assert body["status"] == "unhealthy"
    assert {s["name"]: s["status"] for s in body["services"]}["Database"] == "Not migrated"


def test_every_error_has_code_and_detail(client, auth):
    not_found = client.get("/api/sessions/missing", headers=auth).json()
    unknown_route = client.get("/api/nope").json()
    invalid = client.post("/api/auth/login", json={}).json()
    assert not_found == {"code": "not_found", "detail": "Session not found."}
    assert unknown_route["code"] == "not_found"
    assert invalid["code"] == "validation_error" and invalid["detail"] and invalid["errors"]


def test_database_failure_returns_friendly_503(client):
    def broken_db():
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    app.dependency_overrides[get_db] = broken_db
    response = client.post("/api/auth/login", json={"username": "someone", "password": "something"})
    assert response.status_code == 503 and response.json()["code"] == "database_unavailable"
    assert "db down" not in response.text


def test_unexpected_error_is_friendly_and_keeps_cors_headers(client, auth):
    with patch("app.api.sessions.list_sessions", side_effect=RuntimeError("secret internals")):
        response = client.get("/api/sessions", headers={**auth, "Origin": ORIGIN})
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error" and "secret internals" not in response.text
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["x-frame-options"] == "DENY"


def test_oversized_request_is_rejected(client, auth):
    session_id = new_session(client, auth)
    response = client.post(f"/api/sessions/{session_id}/messages", content=b"x" * (300 * 1024),
                           headers={**auth, "Content-Type": "application/json"})
    assert response.status_code == 413 and response.json()["code"] == "payload_too_large"


def test_security_headers_and_request_id(client):
    response = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert response.headers["x-request-id"] == "abc123"
    assert len(client.get("/api/health").headers["x-request-id"]) == 32


def test_cors_allows_only_configured_origins(client):
    ok = client.options("/api/sessions", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET",
                                                  "Access-Control-Request-Headers": "authorization"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == ORIGIN
    blocked = client.options("/api/sessions", headers={"Origin": "https://evil.example",
                                                       "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in blocked.headers


def test_api_docs_are_disabled_in_production():
    settings = Settings(ENVIRONMENT="production", JWT_SECRET="p" * 48, DATABASE_URL="sqlite://")
    with TestClient(create_app(settings)) as production:
        assert production.get("/docs").status_code == 404
        assert production.get("/openapi.json").status_code == 404


def test_production_requires_a_strong_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(ENVIRONMENT="production", JWT_SECRET="short")


def test_development_generates_a_temporary_secret():
    assert len(Settings(ENVIRONMENT="development", JWT_SECRET="").jwt_secret) >= 32


def test_cors_origins_are_parsed():
    assert Settings(CORS_ORIGINS=" https://a.example , ,https://b.example").cors_origin_list == [
        "https://a.example", "https://b.example"]
