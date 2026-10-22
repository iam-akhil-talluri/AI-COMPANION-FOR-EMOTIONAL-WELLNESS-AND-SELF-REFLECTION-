"""Shared test helpers."""

from fastapi.testclient import TestClient

MOCK_REPLY = "That sounds like a lot to carry. Would it help to pick one small next step?"
PASSWORD = "correct-horse-battery"
ORIGIN = "http://localhost:5173"


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
