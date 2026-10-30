"""Tests for private journal entries: saving, safety screening, privacy, limits and retention."""

from datetime import timedelta

from sqlalchemy import select

from app.config import get_settings
from app.db.models import EventLog, JournalEntry, SafetyEvent
from app.db.types import utc_now
from app.services.retention import purge_expired
from tests.helpers import register

PROMPT = "What has been taking up most of your energy lately?"


def save(client, headers, content, prompt=PROMPT):
    return client.post("/api/journal", json={"content": content, "prompt": prompt}, headers=headers)


def journal(client, headers, query=""):
    response = client.get(f"/api/journal{query}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_save_and_list_newest_first(client, auth):
    first = save(client, auth, "Work has been taking most of my energy.")
    assert first.status_code == 201
    body = first.json()
    assert body["status"] == "ok" and body["risk_level"] == "low" and body["resources"] == []
    assert body["entry"]["prompt"] == PROMPT and body["entry"]["created_at"].endswith("Z")
    save(client, auth, "Today felt lighter after a walk.", prompt=None)

    listed = journal(client, auth)
    assert listed["total"] == 2 and listed["retention_days"] == get_settings().retention_days
    assert [e["content"] for e in listed["entries"]] == ["Today felt lighter after a walk.",
                                                         "Work has been taking most of my energy."]
    assert listed["entries"][0]["prompt"] is None


def test_paging(client, auth):
    for index in range(5):
        save(client, auth, f"Entry {index}")
    page = journal(client, auth, "?limit=2&offset=2")
    assert page["total"] == 5 and [e["content"] for e in page["entries"]] == ["Entry 2", "Entry 1"]


def test_empty_and_too_long_entries_are_rejected(client, auth):
    assert save(client, auth, "   ").json()["code"] == "empty_message"
    too_long = save(client, auth, "a" * (get_settings().max_journal_chars + 1))
    assert too_long.status_code == 422 and too_long.json()["code"] == "message_too_long"
    assert journal(client, auth)["total"] == 0


def test_journal_needs_sign_in(client):
    assert client.get("/api/journal").status_code == 401
    assert client.post("/api/journal", json={"content": "hi"}).status_code == 401


def test_entries_are_private(client, auth):
    entry_id = save(client, auth, "Private thoughts").json()["entry"]["id"]
    other = register(client, "other-user")
    assert journal(client, other) == {"entries": [], "total": 0, "retention_days": get_settings().retention_days}
    assert client.delete(f"/api/journal/{entry_id}", headers=other).status_code == 404
    assert journal(client, auth)["total"] == 1


def test_delete_own_entry(client, db_session, auth):
    entry_id = save(client, auth, "Delete me").json()["entry"]["id"]
    assert client.delete(f"/api/journal/{entry_id}", headers=auth).status_code == 204
    assert journal(client, auth)["total"] == 0
    assert client.delete(f"/api/journal/{entry_id}", headers=auth).status_code == 404
    assert db_session.scalar(select(EventLog).where(EventLog.event_type == "journal_deleted")) is not None


def test_elevated_entry_is_saved_with_support_resources(client, db_session, auth):
    body = save(client, auth, "I can't cope with anything anymore.").json()
    assert body["status"] == "support" and body["risk_level"] == "elevated"
    assert any(r["id"] == "988" for r in body["resources"])
    assert journal(client, auth)["total"] == 1
    event = db_session.scalar(select(SafetyEvent))
    assert event.action == "journal_support_resources" and event.session_id is None


def test_high_risk_entry_is_saved_with_crisis_resources(client, db_session, auth, admin_auth):
    body = save(client, auth, "I want to kill myself.").json()
    assert body["status"] == "crisis" and body["risk_level"] == "high"
    assert {r["id"] for r in body["resources"]} >= {"988", "emergency"}
    assert journal(client, auth)["total"] == 1
    escalations = client.get("/api/admin/analytics", headers=admin_auth).json()["escalations"]
    assert escalations == {"total": 1, "crisis": 1, "support": 0}


def test_no_ai_reads_journal_entries(client, auth, openai):
    save(client, auth, "Work has been a lot this week.")
    save(client, auth, "I can't cope with anything anymore.")
    openai.chat.completions.create.assert_not_called()


def test_moderation_outage_still_saves_with_rules(client, auth, openai, monkeypatch):
    monkeypatch.setattr(get_settings(), "use_openai_moderation", True)
    openai.moderations.create.side_effect = TimeoutError("down")
    ok = save(client, auth, "Work has been a lot this week.")
    risky = save(client, auth, "I want to kill myself.")
    assert ok.status_code == 201 and ok.json()["status"] == "ok"
    assert risky.status_code == 201 and risky.json()["status"] == "crisis"  # the rules still catch it


def test_logs_never_contain_journal_text(client, db_session, auth):
    save(client, auth, "My secret worry about exams")
    save(client, auth, "I can't cope with anything anymore.")
    details = " ".join(e.detail or "" for e in db_session.scalars(select(EventLog)))
    assert "secret" not in details and "cope" not in details
    assert db_session.scalar(select(EventLog).where(EventLog.event_type == "journal_saved")).detail == "risk=low"


def test_journal_is_rate_limited(client, auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "journal_entries_per_hour", 2)
    assert save(client, auth, "One").status_code == 201
    assert save(client, auth, "Two").status_code == 201
    response = save(client, auth, "Three")
    assert response.status_code == 429 and response.json()["code"] == "rate_limited"


def test_journal_off_when_transcripts_are_not_stored(client, auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "store_transcripts", False)
    response = save(client, auth, "Hello")
    assert response.status_code == 403 and response.json()["code"] == "journal_disabled"


def test_retention_deletes_old_entries(client, db_session, auth):
    old_id = save(client, auth, "Old entry").json()["entry"]["id"]
    save(client, auth, "New entry")
    db_session.get(JournalEntry, old_id).created_at = utc_now() - timedelta(days=40)
    db_session.commit()
    assert purge_expired(db_session, retention_days=30) == 1
    assert [e["content"] for e in journal(client, auth)["entries"]] == ["New entry"]


def test_export_includes_own_journal_only(client, auth):
    save(client, auth, "Mine")
    other = register(client, "other-user")
    save(client, other, "Theirs")
    exported = client.get("/api/sessions/export", headers=auth).json()
    assert [e["content"] for e in exported["journal"]] == ["Mine"]
