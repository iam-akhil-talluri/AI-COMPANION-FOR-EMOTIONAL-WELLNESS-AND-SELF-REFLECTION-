"""Shared test helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

MOCK_REPLY = "That sounds like a lot to carry. Would it help to pick one small next step?"
PASSWORD = "correct-horse-battery"
ORIGIN = "http://localhost:5173"
AI_TEXT = "That sounds like a heavy day. What part of it is weighing on you most?"


def completion(text: str = AI_TEXT, prompt_tokens: int = 700, completion_tokens: int = 40):
    """A fake OpenAI chat completion."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        model="gpt-test",
    )


def moderation_result(*flagged: str):
    """A fake OpenAI moderation response flagging the given categories."""
    categories = MagicMock()
    categories.model_dump.return_value = {name: True for name in flagged}
    return SimpleNamespace(results=[SimpleNamespace(categories=categories)])


def register(client: TestClient, username: str = "calm-river", password: str = PASSWORD) -> dict:
    """Register an account and return its Authorization header."""
    response = client.post("/api/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def login(client: TestClient, username: str, password: str = PASSWORD, admin: bool = False):
    return client.post("/api/auth/login", json={"username": username, "password": password, "admin": admin})


def new_session(client: TestClient, headers: dict, **body) -> str:
    response = client.post("/api/sessions", json=body or None, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(client: TestClient, headers: dict, session_id: str, content: str):
    return client.post(f"/api/sessions/{session_id}/messages", json={"content": content}, headers=headers)
