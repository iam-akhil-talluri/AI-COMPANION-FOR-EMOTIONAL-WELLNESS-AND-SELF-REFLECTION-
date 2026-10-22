"""Operational logging and the admin log endpoint."""

import pytest
from sqlalchemy import select

from app.db.models import EventLog
from app.services.event_log import log_event
from tests.helpers import new_session, send


def test_admin_can_read_recent_logs_newest_first(client, auth, admin_auth, fake_replies):
    send(client, auth, new_session(client, auth), "Hello")
    response = client.get("/api/admin/logs", headers=admin_auth)
    assert response.status_code == 200
    logs = response.json()
    events = [entry["event"] for entry in logs]
    # The admin_login event comes from the fixture, before the message.
    assert events[:3] == ["response_generated", "chat_request", "admin_login"]
    assert logs[2] == {"time": logs[2]["time"], "type": "Account", "event": "admin_login",
                       "message": "Administrator signed in", "status": "OK", "environment": "test"}
    assert logs[2]["time"].endswith("Z")


def test_logs_never_contain_message_text(client, auth, admin_auth, fake_replies):
    send(client, auth, new_session(client, auth), "my very private sentence")
    assert "my very private sentence" not in client.get("/api/admin/logs?limit=500", headers=admin_auth).text


def test_logs_require_an_admin(client, auth):
    assert client.get("/api/admin/logs", headers=auth).status_code == 403
    assert client.get("/api/admin/logs").status_code == 401


def test_log_limit_is_respected(client, admin_auth, db_session):
    for _ in range(5):
        log_event(db_session, "user_login")
    db_session.commit()
    assert len(client.get("/api/admin/logs?limit=3", headers=admin_auth).json()) == 3


def test_unknown_event_types_and_levels_are_refused(db_session):
    with pytest.raises(ValueError, match="event type"):
        log_event(db_session, "made_up_event")
    with pytest.raises(ValueError, match="level"):
        log_event(db_session, "user_login", level="loud")


def test_log_detail_is_truncated(db_session):
    log_event(db_session, "api_error", level="error", detail="x" * 500)
    db_session.commit()
    assert len(db_session.scalar(select(EventLog)).detail) == 200
