# Backend: AI Companion for Emotional Wellness & Self-Reflection

FastAPI + MySQL backend: accounts, conversation sessions and their memory,
operational logging, health checks and the Docker image for deployment.

> This system is not therapy, medical care, diagnosis, or crisis intervention.

IT 7993 Capstone, Fall 2026. Sponsor: Capgemini America, Inc. Team P05-01.

## What it does

- **Pseudonymous accounts**: username + password only (Argon2id hashes, JWT sign-in). No email, real name or other personal information. Roles `user` and `admin`; the login screen's "Sign in as Administrator" checkbox is enforced by the server.
- **Conversation and reflection sessions**: create, list (own sessions only), open, delete, and send messages.
- **Conversation memory**: messages are stored per session; the last `CONTEXT_MESSAGES` messages are passed to the reply provider with each new message. A retention job removes old text after `RETENTION_DAYS`.
- **Operational logging**: what happened (event type, level), never what anyone wrote. Admins read it at `GET /api/admin/logs`.
- Rate limits, length limits, one error format, security headers, request IDs, Alembic migrations, health check, Docker image.

## Reply provider (integration point)

The backend does not write replies itself. `app/services/reply_provider.py` is where the safety and AI layer
plugs in with `set_reply_provider()`. Until a provider is registered, `POST /api/sessions/{id}/messages`
**fails closed**: it answers `503 reply_unavailable` and stores nothing.

## Quick start (local)

Requirements: Python 3.12+ (tested on 3.13) and MySQL 8.

```powershell
cd backend
python -m venv .venv                          # macOS / Linux: python3 -m venv .venv
.venv\Scripts\Activate.ps1                    # macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
copy .env.example .env                        # macOS / Linux: cp .env.example .env
```

Create an empty database once (MySQL Workbench or `mysql -u root -p`):

```sql
CREATE DATABASE wellness_companion CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'wellness_app'@'localhost' IDENTIFIED BY 'choose-a-password';
GRANT ALL PRIVILEGES ON wellness_companion.* TO 'wellness_app'@'localhost';
```

Edit `.env`:

```text
DATABASE_URL=mysql+pymysql://wellness_app:choose-a-password@localhost:3306/wellness_companion
JWT_SECRET=<output of: python -c "import secrets; print(secrets.token_urlsafe(48))">
```

Create the tables and an administrator, then run the API:

```powershell
python -m alembic upgrade head
python -m scripts.create_admin --username admin      # prompts for a password (12-128 characters)
python -m uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000, interactive docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Tests and lint

```powershell
python -m pytest -q          # SQLite in memory
python -m ruff check .
```

Run the same suite against a real, **empty, throwaway** MySQL database (all tables are dropped and recreated):

```powershell
$env:TEST_DATABASE_URL="mysql+pymysql://user:pass@localhost:3306/wellness_test"   # macOS / Linux: export TEST_DATABASE_URL=...
python -m pytest -q
```

## Docker

```powershell
docker build -t wellness-backend .
docker run --env-file .env -p 8000:8000 wellness-backend
```

The container applies migrations on start (`RUN_MIGRATIONS=false` turns that off when several instances start at
once) and reports health at `/health`.

## Project layout

```text
backend/
  app/
    main.py            app factory, middleware order, routers
    config.py          every setting (environment variables / .env)
    errors.py          one error shape: {"code", "detail"}
    middleware.py      unexpected-error guard, request size limit, request IDs, security headers
    api/               routes: auth, sessions (+ messages), logs (admin), health
    services/          conversation_service, chat_service, reply_provider, user_service, security,
                       rate_limiter, event_log, retention, health_service
    db/                SQLAlchemy models, UTC datetime type, engine/session
    schemas/           request and response models (the API contract)
  migrations/          Alembic migrations (MySQL schema history)
  scripts/             create_admin.py
  tests/
  Dockerfile, docker-entrypoint.sh
```

## Security

Never commit `.env`. Database credentials and the JWT secret are read from environment variables only and are
never returned by any endpoint. In production (`ENVIRONMENT=production`) the server refuses to start without a
strong `JWT_SECRET`, and the interactive API docs are turned off.
