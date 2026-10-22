"""Tests for sessions, messaging, conversation memory and retention."""

from datetime import timedelta

from sqlalchemy import select, update

from app.config import get_settings
from app.db.models import ConversationSession, EventLog, Message, User
from app.db.types import utc_now
from app.services import reply_provider
from app.services.conversation_service import touch_session
from app.services.retention import purge_expired
from tests.helpers import MOCK_REPLY, new_session, register, send


def test_create_session_returns_summary(client, auth):
    response = client.post("/api/sessions", json={"type": "reflection", "prompt": "What felt hard today?",
                                                  "title": "Reflection: What felt hard today?"}, headers=auth)
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "reflection" and body["prompt"] == "What felt hard today?"
    assert body["message_count"] == 0 and body["created_at"].endswith("Z")


def test_create_session_without_body_defaults_to_conversation(client, auth):
    assert client.post("/api/sessions", headers=auth).json()["type"] == "conversation"


def test_invalid_session_type_rejected(client, auth):
    response = client.post("/api/sessions", json={"type": "journal"}, headers=auth)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"


def test_session_list_only_shows_own_sessions_newest_first(client, auth, fake_replies):
    first = new_session(client, auth)
    second = new_session(client, auth)
    send(client, auth, first, "Hello")
    send(client, auth, second, "Hi")
    send(client, auth, first, "Hello again")  # first is now the most recently active
    other = register(client, "other-user")
    send(client, other, new_session(client, other), "Not yours")
    assert [s["id"] for s in client.get("/api/sessions", headers=auth).json()] == [first, second]


def test_empty_sessions_are_not_listed(client, db_session, auth, fake_replies):
    """Sessions without messages are not listed."""
    used = new_session(client, auth)
    send(client, auth, used, "Hello")
    empty_conversation = new_session(client, auth)
    empty_reflection = new_session(client, auth, type="reflection", prompt="What felt hard?")
    assert [s["id"] for s in client.get("/api/sessions", headers=auth).json()] == [used]
    # Still accessible by ID.
    assert client.get(f"/api/sessions/{empty_conversation}", headers=auth).status_code == 200
    assert client.get(f"/api/sessions/{empty_reflection}", headers=auth).status_code == 200


def test_retention_removes_old_empty_sessions_only(client, db_session, auth, fake_replies):
    old_empty = new_session(client, auth)
    new_empty = new_session(client, auth)
    old_used = new_session(client, auth)
    send(client, auth, old_used, "Hello")
    for session_id in (old_empty, old_used):
        db_session.get(ConversationSession, session_id).last_active = utc_now() - timedelta(days=2)
    db_session.commit()

    assert purge_expired(db_session, retention_days=30) == 1
    db_session.expire_all()
    assert db_session.get(ConversationSession, old_empty) is None
    assert db_session.get(ConversationSession, new_empty) is not None  # may still be in use
    assert db_session.get(ConversationSession, old_used).message_count == 2  # within retention, untouched
    detail = db_session.scalar(select(EventLog.detail).where(EventLog.event_type == "retention_purge"))
    assert detail == "rows=0 sessions=0 empty_sessions=1"


def test_session_detail_and_messages(client, auth, fake_replies):
    session_id = new_session(client, auth)
    send(client, auth, session_id, "Hello")
    detail = client.get(f"/api/sessions/{session_id}", headers=auth).json()
    assert detail["message_count"] == 2
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert [m["content"] for m in detail["messages"]] == ["Hello", MOCK_REPLY]
    assert all(m["created_at"].endswith("Z") for m in detail["messages"])


def test_unknown_and_foreign_sessions_are_404(client, auth, fake_replies):
    session_id = new_session(client, auth)
    other = register(client, "other-user")
    assert client.get(f"/api/sessions/{session_id}", headers=other).status_code == 404
    assert send(client, other, session_id, "Hi").status_code == 404
    assert client.delete(f"/api/sessions/{session_id}", headers=other).status_code == 404
    assert client.get("/api/sessions/does-not-exist", headers=auth).status_code == 404
    fake_replies.assert_not_called()


def test_user_can_delete_session(client, db_session, auth, fake_replies):
    session_id = new_session(client, auth)
    send(client, auth, session_id, "Hello")
    assert client.delete(f"/api/sessions/{session_id}", headers=auth).status_code == 204
    assert db_session.get(ConversationSession, session_id) is None
    assert list(db_session.scalars(select(Message))) == []


def test_deleting_a_user_removes_their_sessions(client, db_session, auth, fake_replies):
    send(client, auth, new_session(client, auth), "Hello")
    db_session.delete(db_session.scalar(select(User)))
    db_session.commit()
    for model in (ConversationSession, Message):
        assert list(db_session.scalars(select(model))) == []


def test_session_counter_survives_concurrent_updates(client, db_session, auth):
    """Two requests in the same session must not overwrite each other's counter."""
    session_id = new_session(client, auth)
    stale = db_session.get(ConversationSession, session_id)  # this request loaded message_count=0
    # Meanwhile another request finished a turn and its update reached the database.
    db_session.execute(
        update(ConversationSession).where(ConversationSession.id == session_id)
        .values(message_count=10).execution_options(synchronize_session=False)
    )
    touch_session(stale, added=2)
    db_session.commit()
    db_session.refresh(stale)
    assert stale.message_count == 12


def test_reply_is_returned_and_saved(client, auth, fake_replies):
    session_id = new_session(client, auth)
    response = send(client, auth, session_id, "  I had a long day.  ")
    assert response.status_code == 200
    body = response.json()
    assert body == {"session_id": session_id, "status": "ok", "response": MOCK_REPLY,
                    "created_at": body["created_at"]}
    assert body["created_at"].endswith("Z")
    fake_replies.assert_called_once_with([], "I had a long day.")


def test_provider_receives_the_conversation_so_far(client, auth, fake_replies):
    session_id = new_session(client, auth)
    send(client, auth, session_id, "First")
    send(client, auth, session_id, "Second")
    context, message = fake_replies.call_args.args
    assert message == "Second"
    assert context == [{"role": "user", "content": "First"}, {"role": "assistant", "content": MOCK_REPLY}]


def test_memory_is_limited_to_the_most_recent_messages(client, auth, fake_replies, monkeypatch):
    monkeypatch.setattr(get_settings(), "context_messages", 3)
    session_id = new_session(client, auth)
    for text in ("one", "two", "three"):
        send(client, auth, session_id, text)
    context, _ = fake_replies.call_args.args
    assert [m["content"] for m in context] == [MOCK_REPLY, "two", MOCK_REPLY]


def test_memory_is_per_session(client, auth, fake_replies):
    first = new_session(client, auth)
    send(client, auth, first, "Only in the first session")
    second = new_session(client, auth)
    send(client, auth, second, "Hello")
    context, _ = fake_replies.call_args.args
    assert context == []


def test_first_message_titles_the_conversation(client, auth, fake_replies):
    session_id = new_session(client, auth)
    send(client, auth, session_id, "Work has been really stressful this whole week")
    send(client, auth, session_id, "Another message")
    assert client.get(f"/api/sessions/{session_id}", headers=auth).json()["title"] == "Work has been really stressful this..."


def test_reflection_keeps_its_own_title(client, auth, fake_replies):
    session_id = new_session(client, auth, type="reflection", title="Reflection: What felt hard?")
    send(client, auth, session_id, "Many things")
    assert client.get(f"/api/sessions/{session_id}", headers=auth).json()["title"] == "Reflection: What felt hard?"


def test_without_a_provider_nothing_is_stored(client, db_session, auth):
    session_id = new_session(client, auth)
    response = send(client, auth, session_id, "Hello")
    assert response.status_code == 503 and response.json()["code"] == "reply_unavailable"
    assert list(db_session.scalars(select(Message))) == []
    assert db_session.get(ConversationSession, session_id).message_count == 0
    error = db_session.scalar(select(EventLog).where(EventLog.event_type == "api_error"))
    assert error is not None and error.level == "error"


def test_failing_provider_fails_closed(client, db_session, auth):
    def broken(context, message):
        raise reply_provider.ReplyUnavailableError("upstream down")

    reply_provider.set_reply_provider(broken)
    session_id = new_session(client, auth)
    assert send(client, auth, session_id, "Hello").status_code == 503
    assert list(db_session.scalars(select(Message))) == []


def test_empty_message_is_rejected(client, auth, fake_replies):
    response = send(client, auth, new_session(client, auth), "   ")
    assert response.status_code == 422 and response.json()["code"] == "empty_message"
    fake_replies.assert_not_called()


def test_long_message_is_rejected(client, auth, fake_replies):
    response = send(client, auth, new_session(client, auth), "a" * 2001)
    assert response.status_code == 422 and response.json()["code"] == "message_too_long"
    fake_replies.assert_not_called()


def test_conversation_length_limit(client, auth, fake_replies, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_messages_per_session", 4)
    session_id = new_session(client, auth)
    assert [send(client, auth, session_id, f"m{n}").status_code for n in range(3)] == [200, 200, 429]
    assert send(client, auth, session_id, "again").json()["code"] == "conversation_limit"


def test_messages_are_rate_limited_per_user(client, db_session, auth, fake_replies, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 2)
    session_id = new_session(client, auth)
    codes = [send(client, auth, session_id, f"m{n}").status_code for n in range(3)]
    assert codes == [200, 200, 429]
    assert db_session.scalar(select(EventLog).where(EventLog.event_type == "rate_limit_triggered")) is not None


def test_without_transcripts_no_text_is_stored(client, db_session, auth, fake_replies, monkeypatch):
    monkeypatch.setattr(get_settings(), "store_transcripts", False)
    session_id = new_session(client, auth)
    assert send(client, auth, session_id, "Private").status_code == 200
    assert list(db_session.scalars(select(Message))) == []
    conversation = db_session.get(ConversationSession, session_id)
    assert conversation.message_count == 2 and conversation.title == "Conversation"


def test_retention_purges_old_text_and_hides_session(client, db_session, auth, fake_replies):
    old = new_session(client, auth)
    send(client, auth, old, "Hello")
    recent = new_session(client, auth)
    send(client, auth, recent, "Hi")
    db_session.get(ConversationSession, old).last_active = utc_now() - timedelta(days=40)
    db_session.commit()

    assert purge_expired(db_session, retention_days=30) == 2  # the old session's 2 messages
    assert db_session.get(ConversationSession, old).transcript_purged_at is not None
    assert [s["id"] for s in client.get("/api/sessions", headers=auth).json()] == [recent]
    assert db_session.scalar(select(EventLog).where(EventLog.event_type == "retention_purge")) is not None
    assert purge_expired(db_session, retention_days=30) == 0  # idempotent


def test_retention_disabled_with_zero_days(db_session):
    assert purge_expired(db_session, retention_days=0) == 0


def test_retention_job_uses_its_own_session(session_factory, client, auth):
    from app.services.retention import _purge_once

    _purge_once(30)  # nothing to purge, must not raise
