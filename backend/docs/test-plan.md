# Test Plan: Akhil's Backend Work and the Frontend Integration

From: Akhil (backend, database, repository setup, sessions and conversation memory, logging, deployment support)

## 1. Scope

**In scope (Akhil's responsibilities and the frontend integration):**

| Area | What is tested |
|---|---|
| Backend | App startup, configuration, error format, security headers, request IDs, CORS, size limit, rate limits, accounts and roles |
| Database | Migrations (upgrade, downgrade, re-upgrade), schema, foreign-key cascades, UTC dates, admin script |
| Sessions and conversation memory | Create, list, open, delete sessions; ownership; message saving; memory window; titles; limits; retention purge |
| Logging | Event log rows, allowed event types, no message text in logs, admin log endpoint, console log format |
| Repository setup | Ignored secrets, templates present, clean install from `requirements-dev.txt` |
| Deployment support | Container start script (migrations + server), health endpoint, production settings |
| Frontend integration | Every connected screen, end to end in a real browser, plus lint and production build |

**Out of scope (other members), tested only as far as the current setup allows:**

| Area | Owner | Limited test |
|---|---|---|
| Safety screening and AI replies | Emmanuel | Message flow with a stand-in reply source (scratch folder only); failing reply source; no reply source |
| Crisis / support routing, Safety Check Unavailable | Emmanuel | Static screens reachable and render; links present |
| My Insights, admin statistics, cost card | Korey | Screens render without errors using sample data |
| Journal, coping tools | Not assigned | Exercises work in the browser; nothing is sent to the backend |
| AWS deployment | Shaheed | Not tested (no AWS access) |

## 2. Test environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| Python | 3.13 (virtual environment with `requirements-dev.txt`) |
| Node | 22 (Vite 8, oxlint) |
| Database | SQLite file per run (MySQL tests not run, see section 6) |
| Browser | Built-in browser of the Claude desktop app |
| Backend | `uvicorn` on http://127.0.0.1:8000; Vite dev server on http://localhost:5173 with the `/api` proxy |
| Test data | Test accounts created during the run (`calm-river`, `quiet-harbor`, `site-admin`); no real user data |

## 3. Test levels and approach

1. **Automated backend suite:** `pytest` (78 tests) and `ruff`.
2. **Live API tests:** a scripted run against the real running server, so the HTTP layer, middleware and database are
   exercised together (not the in-process test client).
3. **Database, scripts, repository and deployment checks:** commands run by hand, with the results recorded.
4. **End-to-end browser tests:** the real frontend against the real backend.
5. **Limited tests of other members' areas** (section 1).

## 4. Test cases

### 4.1 Backend: automated suite (BA)

| ID | Test | Expected |
|---|---|---|
| BA-01 | `python -m pytest -q` | All pass (78 at the first run; 82 after the defect fixes) |
| BA-02 | `python -m ruff check .` | No issues |

### 4.2 Backend: live API (API)

| ID | Test | Expected |
|---|---|---|
| API-01 | `GET /health` and `/api/health` | 200, status healthy, 3 services, no secrets |
| API-02 | Security headers and `X-Request-ID` on API responses | `nosniff`, `DENY`, `no-store`, CSP; request id echoed |
| API-03 | CORS preflight from allowed vs other origin | Allowed origin echoed; other origin gets no CORS header |
| API-04 | Register valid account | 201, token, role `user` |
| API-05 | Register duplicate (different case) | 409 `username_taken` |
| API-06 | Register invalid username / short password | 422 `validation_error` |
| API-07 | Login correct / wrong password / unknown user | 200 / 401 / 401 with identical message |
| API-08 | Login with `admin: true` as normal user / as admin | 403 `admin_required` / 200 role `admin` |
| API-09 | 5 failed logins then a 6th | 6th is 429 `rate_limited` |
| API-10 | `GET /api/auth/me` with valid / missing / garbage token | 200 / 401 `not_authenticated` / 401 `session_expired` |
| API-11 | Logout, then reuse the old token | 204, then 401 |
| API-12 | Create conversation and reflection sessions; invalid type | 201 / 201 / 422 |
| API-13 | List sessions: only own, newest activity first | Correct order and ownership |
| API-14 | Another user's session: get, send, delete | 404 for all |
| API-15 | Send message with no reply provider | 503 `reply_unavailable`, nothing saved, `api_error` logged |
| API-16 | Send message with stand-in provider | 200, both messages saved, count +2, title from first 6 words |
| API-17 | Conversation memory | Provider receives earlier messages oldest first, limited to `CONTEXT_MESSAGES` |
| API-18 | Empty / 2,001-character message | 422 `empty_message` / `message_too_long` |
| API-19 | Conversation limit (`MAX_MESSAGES_PER_SESSION`) | 429 `conversation_limit` |
| API-20 | Message rate limit (`RATE_LIMIT_PER_MINUTE`) | 429 `rate_limited` with `Retry-After` |
| API-21 | Body over 256 KB | 413 `payload_too_large` |
| API-22 | Delete session | 204, then 404 on get |
| API-23 | `GET /api/admin/logs` as admin / user / anonymous | 200 / 403 / 401 |
| API-24 | Unknown route | 404 `{code, detail}` |
| API-25 | Extra request fields (e.g. `mode`) | Ignored, request accepted |

### 4.3 Database (DB)

| ID | Test | Expected |
|---|---|---|
| DB-01 | `alembic upgrade head` on an empty database | 4 tables + `alembic_version` |
| DB-02 | `alembic downgrade base`, then `upgrade head` again | Clean down and up |
| DB-03 | Schema matches the models | Covered by BA-01 (`test_migrations_match_the_models`) |
| DB-04 | Deleting a user removes their sessions and messages | Cascade works |
| DB-05 | Dates are stored and returned as UTC (`Z`) | ISO strings end in `Z` |
| DB-06 | MySQL 8 run (`TEST_DATABASE_URL`) | **Not run**: no throwaway MySQL database or test credentials available |

### 4.4 Sessions, memory and retention (SM)

| ID | Test | Expected |
|---|---|---|
| SM-01 | `STORE_TRANSCRIPTS=false` | Reply returned, no message text stored, count still +2 |
| SM-02 | Retention purge at startup for a session older than `RETENTION_DAYS` | Messages deleted, session hidden from list, `retention_purge` logged |
| SM-03 | Recent sessions untouched by the purge | Still listed with messages |

### 4.5 Logging (LG)

| ID | Test | Expected |
|---|---|---|
| LG-01 | Events written for register, login, failed login, chat, errors, rate limit | Rows in `event_logs` |
| LG-02 | No message text or usernames in `event_logs` | Search finds none |
| LG-03 | Console log line format | `time LEVEL name message` |
| LG-04 | Admin log entries have labels, status and UTC time | Matches the documented shape |

### 4.6 Scripts (SC)

| ID | Test | Expected |
|---|---|---|
| SC-01 | `create_admin` creates an admin (password from an environment variable) | Admin can sign in with the box ticked |
| SC-02 | `create_admin --keep-password` promotes an existing user | User becomes admin |
| SC-03 | Admin password shorter than 12 characters | Refused |

### 4.7 Repository setup (RS)

| ID | Test | Expected |
|---|---|---|
| RS-01 | `.env`, `backend/.env`, `backend/data/*.db`, `.venv` are ignored by git | `git check-ignore` matches |
| RS-02 | No secrets in tracked or new files (keys, passwords, JWT secrets) | None found |
| RS-03 | Templates present: root `.env.example`, `backend/.env.example` | Present, placeholders only |
| RS-04 | Fresh virtual environment from `requirements-dev.txt` | Installs; tests pass in it |

### 4.8 Deployment support (DP)

| ID | Test | Expected |
|---|---|---|
| DP-01 | Run `docker-entrypoint.sh` (migrations, then server) outside Docker | Migrates an empty database and serves `/health` |
| DP-02 | `RUN_MIGRATIONS=false` | Server starts without running migrations |
| DP-03 | `ENVIRONMENT=production` with a short `JWT_SECRET` | Refuses to start |
| DP-04 | Production: API docs off | `/docs` and `/openapi.json` return 404 |
| DP-05 | Docker image build | **Not run**: Docker is not installed; Dockerfile reviewed instead |

### 4.9 Frontend integration, end to end (FE)

| ID | Test | Expected |
|---|---|---|
| FE-01 | `npm run lint`, `npm run build` | 0 issues; build succeeds |
| FE-02 | First load without a token | Loading, then Login |
| FE-03 | Create account (valid) | Home with "Welcome, <name>!" |
| FE-04 | Create account: taken username / invalid username / short password | Server or browser message shown, stays on form |
| FE-05 | Sign in: wrong password; non-admin with Administrator box | Correct messages |
| FE-06 | Admin sign-in | Admin Home |
| FE-07 | Reload keeps sign-in; Sign Out clears token and data | As described |
| FE-08 | Expired / invalid token during use | Back to Login with "Your sign-in has expired…" |
| FE-09 | History empty state | "No conversations yet…" |
| FE-10 | Start a Conversation, send 2 messages (stand-in provider) | Replies shown; memory visible in the replies |
| FE-11 | History lists it with the server title and count; Continue loads messages; send more | Correct |
| FE-12 | Reflection: Use This Prompt → chat → History → Back to History | Correct |
| FE-13 | Delete a session from History | Removed, also on the server |
| FE-14 | No reply provider: send | Notice bubble, text restored, nothing saved |
| FE-15 | Rate limit / conversation limit during chat | Notice with the server message, text restored |
| FE-16 | Backend stopped: sign in and send | "We could not reach the server…" |
| FE-17 | Second account in same tab | Sees none of the first user's data |
| FE-18 | Admin: Recent Log Events and Architecture Health | Real data; Safety/AI "Not connected yet" |
| FE-19 | Input limits: 2,000 characters on chat inputs; username/password limits | `maxLength` present |
| FE-20 | Browser console during the run | No application errors (expected HTTP error logs only) |
| FE-21 | Phone-width layout of changed screens (Login, History) | No overlap, buttons usable |

### 4.10 Other members' areas, limited (OT)

| ID | Test | Expected |
|---|---|---|
| OT-01 | Stand-in reply provider exercises the reply path | Covered by FE-10/11/12 and API-16/17 |
| OT-02 | Failing reply provider | 503, nothing saved (BA-01) |
| OT-03 | Support bar → Support & Crisis Resources; Safety Check Unavailable screen renders | Static content and links present |
| OT-04 | My Insights and admin sample cards render | No errors |
| OT-05 | Coping tools: breathing, journal, grounding | Work locally; no backend calls |

## 5. Entry and exit criteria

- **Entry:** the backend and frontend run locally; the test accounts are created during the run.
- **Exit:** every in-scope case is run and recorded as Pass, Fail or Not run (with the reason). Every failure is
  logged in the test report with steps, cause and fix status.

## 6. Known limitations

- **MySQL:** the only MySQL database on this machine belongs to the newer project, and its credentials are in a real
  configuration file. The suite drops and recreates tables, so it must only ever run against an **empty, throwaway**
  database. Run it with:
  `TEST_DATABASE_URL=mysql+pymysql://<user>:<pass>@localhost:3306/<empty_test_db> python -m pytest -q`.
- **Docker:** not installed. The container start script is tested directly instead (DP-01/02).
- **AI and safety:** not implemented in this backend (Emmanuel). Replies are tested with a stand-in reply source kept
  outside the project.

## 7. Deliverable

The results, with an error log, go in `test-report.md`.
