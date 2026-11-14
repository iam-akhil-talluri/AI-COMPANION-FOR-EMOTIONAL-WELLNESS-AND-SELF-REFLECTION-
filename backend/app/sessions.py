"""In-memory conversation history, keyed by session id.

Placeholder until the MySQL layer exists: history is lost on restart and is not
shared between worker processes.
"""

from typing import Any

_sessions: dict[str, list[dict[str, Any]]] = {}


def get_history(session_id: str) -> list[dict[str, Any]]:
    return _sessions.setdefault(session_id, [])


def seed_history(session_id: str, messages: list[tuple[str, str]]) -> None:
    """Load (role, text) pairs from the frontend into a session with no history."""
    history = get_history(session_id)
    if history:
        return
    turns = [(r, t) for r, t in messages if r in ("user", "assistant") and t.strip()]
    # Start the conversation with a user turn.
    while turns and turns[0][0] != "user":
        turns.pop(0)
    history.extend({"role": r, "content": t} for r, t in turns)


def append_turn(session_id: str, user_text: str, assistant_text: str) -> None:
    history = get_history(session_id)
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
