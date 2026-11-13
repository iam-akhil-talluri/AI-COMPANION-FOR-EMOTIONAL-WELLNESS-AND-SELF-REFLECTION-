"""Offline tests for /chat: the model call is replaced with a fake."""

import pytest
from fastapi.testclient import TestClient

from app import main, rag, sessions
from app.llm import CompanionError
from app.safety import ESCALATION_MESSAGE

client = TestClient(main.app)


@pytest.fixture
def fake_model(monkeypatch):
    calls = []
    reply = {"value": ("ok", "That sounds hard. What's on your mind?")}

    async def fake_generate_reply(history, user_text, context=""):
        calls.append({"history": list(history), "user_text": user_text, "context": context})
        if isinstance(reply["value"], Exception):
            raise reply["value"]
        return reply["value"]

    async def no_retrieval(query):
        return []

    monkeypatch.setattr(main, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(rag, "retrieve", no_retrieval)
    monkeypatch.setattr(sessions, "_sessions", {})
    return calls, reply


def post(message, session_id="s1", history=None):
    body = {"message": message, "session_id": session_id, "history": history or []}
    return client.post("/chat", json=body).json()


def test_ok_reply_is_passed_through(fake_model):
    res = post("I've been stressed about work")
    assert res == {
        "status": "ok",
        "message": "That sounds hard. What's on your mind?",
        "session_id": "s1",
        "sources": [],
    }


def test_out_of_scope_reply_is_passed_through(fake_model):
    _, reply = fake_model
    reply["value"] = ("out_of_scope", "I can't help with recipes, but how are you feeling?")
    assert post("Give me a recipe")["status"] == "out_of_scope"


def test_rules_escalate_without_calling_model(fake_model):
    calls, _ = fake_model
    res = post("I want to kill myself")
    assert res["status"] == "concern"
    assert res["message"] == ESCALATION_MESSAGE
    assert calls == []


def test_model_concern_is_replaced_with_predefined_message(fake_model):
    _, reply = fake_model
    reply["value"] = ("concern", "model-written text that must not reach the user")
    res = post("It will all be over soon")
    assert res["status"] == "concern"
    assert res["message"] == ESCALATION_MESSAGE


def test_model_failure_returns_error_status(fake_model):
    _, reply = fake_model
    reply["value"] = CompanionError("api error")
    assert post("Hello")["status"] == "error"


def test_numeric_session_id_from_frontend_is_accepted(fake_model):
    res = client.post("/chat", json={"message": "Hi", "session_id": 1761100000000}).json()
    assert res["session_id"] == "1761100000000"


def test_history_accumulates_within_a_session(fake_model):
    calls, _ = fake_model
    post("First message")
    post("Second message")
    assert calls[1]["history"][0] == {"role": "user", "content": "First message"}
    assert len(calls[1]["history"]) == 2


def test_frontend_history_seeds_an_unknown_session(fake_model):
    calls, _ = fake_model
    history = [
        {"role": "assistant", "text": "What would you like to reflect on?"},
        {"role": "user", "text": "My exams"},
        {"role": "assistant", "text": "Tell me more."},
    ]
    post("I'm worried I'll fail", session_id="restored", history=history)
    # The leading assistant prompt is dropped so the conversation starts with a user turn.
    assert calls[0]["history"] == [
        {"role": "user", "content": "My exams"},
        {"role": "assistant", "content": "Tell me more."},
    ]
