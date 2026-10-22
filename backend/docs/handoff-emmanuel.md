# Handoff for Emmanuel: connecting safety and AI to the backend

From: Akhil (backend, database, sessions and conversation memory, logging, deployment support)

The backend is in `backend/`. It handles accounts, sessions, conversation memory, logging and health checks.
**It does not contain any safety or AI code.** Those are yours. This document explains the one place where your
work plugs in, what the backend already does for you, and what it expects in return.

## 1. What already exists (you don't need to build it)

| Area | Where | What it does |
|---|---|---|
| Accounts | `app/api/auth.py`, `app/services/user_service.py` | Pseudonymous sign-up and sign-in, admin role |
| Sessions | `app/api/sessions.py`, `app/services/conversation_service.py` | Create, list, open and delete sessions; each user sees only their own |
| Sending a message | `app/services/chat_service.py` | Validates the message, applies rate and length limits, loads memory, asks **your** code for a reply, saves both messages |
| Conversation memory | `recent_context()` in `conversation_service.py` | The last `CONTEXT_MESSAGES` (default 8) messages of the session, oldest first |
| Logging | `app/services/event_log.py` | Operational events without message text; admins read them at `GET /api/admin/logs` |
| Limits | `app/config.py` | 2,000 characters per message, 100 messages per session, 10 per minute and 120 per hour per user |

## 2. The integration point: `app/services/reply_provider.py`

The backend does not write replies itself. It calls a **reply provider** function that you register:

```python
from app.services.reply_provider import set_reply_provider

def companion_reply(context: list[dict], message: str) -> str:
    ...
    return reply_text

set_reply_provider(companion_reply)
```

### What you receive

- `message`: the user's new message, already trimmed, non-empty, and at most `MAX_MESSAGE_CHARS` (2,000) characters.
- `context`: the earlier messages of the same session, **oldest first, not including the new message**, at most
  `CONTEXT_MESSAGES` (default 8) items:

  ```python
  [
      {"role": "user", "content": "I had a long day."},
      {"role": "assistant", "content": "That sounds tiring. What made it long?"},
  ]
  ```

  `role` is always `"user"` or `"assistant"`. It is an empty list for the first message of a session. There is no
  system prompt in it; adding your system prompt is up to you.

### What you return

The reply text as a plain `str`. The backend saves it word for word and sends it to the frontend in the `response`
field. So **your provider must run its output safety check and any clean-up before returning**.

### How to fail, and what the user sees

| Your provider does this | API answers | Saved to the database |
|---|---|---|
| Returns a string | `200` with your reply | Both messages, the counter is updated, and a log event is written |
| Raises `ReplyUnavailableError` (from `reply_provider.py`) | `503 {"code": "reply_unavailable", ...}` and an `api_error` log event | Nothing else |
| Raises `AppError(code, status, detail)` (from `app/errors.py`) | Your status, `{"code": code, "detail": detail}` | Nothing |
| Raises any other exception | `500 {"code": "internal_error", ...}` (details hidden from the user) | Nothing |

I checked these cases: when the provider fails, no messages are stored.

**Fail closed:** run the safety check **before** any AI call. If the safety check itself can't run, raise an error
instead of calling the AI. A good way to tell the frontend is
`AppError("safety_unavailable", 503, "<message for the user>")`. The new frontend version already opens the
"Safety Check Unavailable" screen for that code.

### Where to register it

Register the provider once, when the app starts. The simplest place is `create_app()` in `app/main.py`:

```python
from app.services import reply_provider
from app.services.companion import companion_reply   # your module

def create_app(settings=None):
    ...
    reply_provider.set_reply_provider(companion_reply)
    return app
```

Until a provider is registered, the server logs a warning at startup and every message returns `503 reply_unavailable`.
Session create, list, open and delete keep working.

## 3. What the current API cannot express yet (talk to me first)

The message response today is only:

```json
{ "session_id": "…", "status": "ok", "response": "…", "created_at": "2026-10-21T20:30:00Z" }
```

Your design will probably need more than this, for example:

- `status` values `support` and `crisis`, so the frontend can show support cards or open the crisis screen
- a `resources` list (helplines) and a `risk_level`
- storing risk levels or safety events in the database

These are changes to the shared API contract and the database, so **please tell me what you need and I'll make the
backend changes with you**. Then Cynthia's frontend and the database stay in step. In particular:

- **Response fields:** a provider can only return a string today. We would change the return type to a small result
  object and extend `ChatResponse` in `app/schemas/sessions.py`.
- **New tables or columns:** these go in a new Alembic migration (`0002_...`), never in edits to `0001`. After
  changing `app/db/models.py`, run `python -m alembic revision --autogenerate -m "describe change"`. The test
  `test_migrations_match_the_models` fails if the models and migrations disagree.

## 4. Settings, secrets and dependencies

The backend has no AI settings today. When you add them:

1. Add the fields to `Settings` in `app/config.py`, for example `OPENAI_API_KEY`, the model name and a timeout.
   Follow the existing pattern: `Field(default=..., validation_alias="NAME")`.
2. Document them in `backend/.env.example`, with placeholder values only.
3. Add packages such as `openai` to `backend/requirements.txt` with a pinned version.
4. **Never commit a real key.** `.env` is git-ignored; keys go in `.env` locally and in AWS secrets in production.

## 5. Logging rules

- Use `log_event(db, event_type, session_id, level, detail)` from `app/services/event_log.py`. The caller commits.
- Only the event types in `EVENT_TYPES` are allowed. To add one (for example `safety_check` or `escalation_triggered`),
  add it to `EVENT_TYPES` **and** give it a display label in `_LOG_LABELS` in the same file.
- **Never log what the user wrote.** Log categories, risk levels, timings and error types only. `detail` is cut to
  200 characters.
- Your provider receives no database session today. If you need to write log rows, tell me and we'll pass `db`
  through. Python logging (`logging.getLogger(__name__)`) works as it is.

## 6. Testing your code

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
```

- Tests use an in-memory SQLite database and **never call a real AI**. Keep it that way: mock the OpenAI client in
  your tests.
- `tests/conftest.py` resets the provider to `None` before every test. The `fake_replies` fixture registers a mock
  provider that returns a fixed reply. In your tests, register your own provider (or patch the AI client inside it).
- Helpers in `tests/helpers.py`: `register()`, `new_session()`, `send()`.
- Put your tests in new files, for example `tests/test_safety.py` and `tests/test_ai.py`.

## 7. Reference implementation

A complete safety and AI layer was drafted in the newer project folder
(`AI-COMPANION-FOR-EMOTIONAL-WELLNESS-AND-SELF-REFLECTION-/backend/app/services/`): `safety_service.py`,
`escalation.py`, `ai_service.py`, `chat_pipeline.py`, plus `app/content/` for the system prompt, safety templates and
crisis resources. It was **not** copied here because it is your area. Use it as a starting point if it helps, but
review it as your own work.

## 8. Checklist

- [ ] Write the provider: input safety check → AI call (with `context` and your system prompt) → output safety check → return text
- [ ] Fail closed when the safety check can't run
- [ ] Register the provider in `app/main.py`
- [ ] Add AI settings to `config.py` and `.env.example`, and pinned packages to `requirements.txt`
- [ ] Agree with Akhil on any extra response fields (`support` / `crisis`, `resources`) or database changes
- [ ] Add tests; `pytest` and `ruff check` pass
- [ ] Verify every crisis phone number with the team before the demo
