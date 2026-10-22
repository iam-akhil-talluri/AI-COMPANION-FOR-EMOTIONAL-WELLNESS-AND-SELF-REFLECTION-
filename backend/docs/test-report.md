# Test Report: Akhil's Backend Work and the Frontend Integration

From: Akhil (backend, database, repository setup, sessions and conversation memory, logging, deployment support)

Test plan: `test-plan.md` (same folder). Test date: 21 October 2026. Environment: Windows 11, Python 3.13 (fresh
virtual environment from `requirements-dev.txt`), Node 22, SQLite, and the built-in browser of the Claude desktop app.

## 1. Summary

| Result | Count |
|---|---|
| Test cases in the plan | 78 |
| Run | 76 |
| Passed (after the fixes in section 3) | 76 (including OT-03, run partly) |
| Failed | 0 (FE-16 failed in the first run; passes after the D-3 fix) |
| Not run | 2 (DB-06 MySQL, DP-05 Docker), plus the Safety Check Unavailable part of OT-03 |
| **Product defects logged** | **5**: all fixed and re-tested (D-1 to D-5); **0 open** |
| Test-script errors (not product defects), corrected and re-run | 4 |

**Overall:** every core function in Akhil's area works end to end. That covers accounts, sessions, conversation memory,
history, retention, logging, migrations, the admin script, repository setup, the container start script and the
frontend integration. The defects found are usability and robustness issues; none loses or exposes data. D-1, D-3,
D-4 and D-5 were fixed on 21 October 2026 and re-tested, followed by D-2 (section 3.1). **No defects are open.**

## 2. Results by area

### 2.1 Backend: automated suite

| ID | Result | Notes |
|---|---|---|
| BA-01 `pytest` | Pass | 78 passed in the first run; **82 passed** after the fixes (4 new tests: D-1, D-5 and two for D-2) |
| BA-02 `ruff` | Pass | No issues |

### 2.2 Backend: live API (real server over HTTP, fresh SQLite database per scenario)

| ID | Result | ID | Result | ID | Result |
|---|---|---|---|---|---|
| API-01 Health | Pass | API-10 Who am I / tokens | Pass | API-19 Conversation limit | Pass |
| API-02 Security headers | Pass | API-11 Logout revokes | Pass | API-20 Message rate limit | Pass (after test fix H-1) |
| API-03 CORS | Pass | API-12 Create sessions | Pass | API-21 Oversized body | Pass |
| API-04 Register | Pass | API-13 Own sessions, order | Pass | API-22 Delete session | Pass |
| API-05 Duplicate username | Pass | API-14 Others' sessions 404 | Pass | API-23 Admin logs access | Pass |
| API-06 Invalid input | Pass | API-15 No provider: 503 | Pass | API-24 Unknown route | Pass |
| API-07 Login variants | Pass | API-16 Reply saved, title | Pass | API-25 Extra fields ignored | Pass |
| API-08 Admin check | Pass | API-17 Memory window | Pass | | |
| API-09 Login lockout | Pass | API-18 Empty / too long | Pass | | |

API-17 detail: with `CONTEXT_MESSAGES=3`, the third message's reply provider received exactly the 3 most recent
earlier messages, oldest first (`assistant, user "two", assistant`). The first message received an empty context.

### 2.3 Database

| ID | Result | Notes |
|---|---|---|
| DB-01 Upgrade on empty database | Pass | `event_logs`, `messages`, `sessions`, `users`, `alembic_version` |
| DB-02 Downgrade, re-upgrade | Pass | Only `alembic_version` left after downgrade; clean re-upgrade to `0001 (head)` |
| DB-03 Schema matches models | Pass | Via BA-01 |
| DB-04 Cascade delete | Pass | Deleting a user removed their sessions and messages |
| DB-05 UTC dates | Pass | All timestamps returned as ISO strings ending in `Z` |
| DB-06 MySQL 8 | **Not run** | No throwaway MySQL database or test credentials; see section 5 |

### 2.4 Sessions, memory and retention

| ID | Result | Notes |
|---|---|---|
| SM-01 `STORE_TRANSCRIPTS=false` | Pass | Reply returned, 0 message rows stored, count still +2 |
| SM-02 Retention purge at startup | Pass | 40-day-old session: messages deleted, hidden from History, one `retention_purge` event |
| SM-03 Recent session untouched | Pass | Still listed with both messages |

### 2.5 Logging

| ID | Result | Notes |
|---|---|---|
| LG-01 Events recorded | Pass | `user_registered`, `user_login`, `admin_login`, `login_failed`, `chat_request`, `api_error`, `response_generated`, `rate_limit_triggered`, `retention_purge` |
| LG-02 No text or usernames in the log | Pass | Searched every `detail` value for message text, usernames and passwords: none |
| LG-03 Console format | Pass | `2026-10-21 … INFO app.events event=… session=… detail=…` |
| LG-04 Admin log entry shape | Pass | `time` (UTC, `Z`), `type`, `event`, `message`, `status`, `environment` |

### 2.6 Scripts

| ID | Result | Notes |
|---|---|---|
| SC-01 Create admin | Pass | Created; signed in with the Administrator box (API-08, FE-06) |
| SC-02 Promote existing user | Pass | `promote-me` became `admin` without a password change |
| SC-03 Short admin password | Pass | Refused: "Admin passwords must be 12-128 characters" (exit code 1) |

### 2.7 Repository setup

| ID | Result | Notes |
|---|---|---|
| RS-01 Ignored files | Pass | `.env`, `.env.local`, `backend/.env`, `backend/data/*.db`, `.venv`, caches, `node_modules`, `dist` ignored; both `.env.example` files trackable |
| RS-02 Secret scan | Pass | Only deliberately fake values in tests (`JWT_SECRET="short"`) |
| RS-03 Templates | Pass | Placeholders only (`USER:PASSWORD`, empty `JWT_SECRET`, empty `VITE_API_URL`) |
| RS-04 Clean install | Pass | Fresh virtual environment from `requirements-dev.txt`; BA-01 and BA-02 pass in it; `openai` correctly not installed |

### 2.8 Deployment support

| ID | Result | Notes |
|---|---|---|
| DP-01 Start script with migrations | Pass | Migrated an empty database, then served `/health` 200 |
| DP-02 `RUN_MIGRATIONS=false` | Pass (after harness fix H-2) | Started without migrating (0 tables). After the D-5 fix, `/health` correctly answers 503 "Not migrated" |
| DP-03 Production + short `JWT_SECRET` | Pass | Refused to start: "JWT_SECRET must be at least 32 characters in production" |
| DP-04 Production docs off | Pass (after harness fix H-2) | `/docs`, `/openapi.json`, `/redoc` 404; `/health` 200; no `Server` header |
| DP-05 Docker image build | **Not run** | Docker not installed; Dockerfile reviewed (Python 3.13 slim, non-root user, health check on `/health`) |

### 2.9 Frontend integration (real browser against the real backend)

| ID | Result | Notes |
|---|---|---|
| FE-01 Lint and build | Pass | oxlint 0 issues; build succeeds |
| FE-02 First load without a token | Pass | Login shown; no token |
| FE-03 Create account | Pass | "Welcome, calm-river!" |
| FE-04 Create-account errors | Pass | Short password blocked by the browser; taken username shows the right message. The invalid-username message was technical (D-1); **fixed and re-tested** |
| FE-05 Sign-in errors | Pass | Wrong password and non-admin messages correct |
| FE-06 Admin sign-in | Pass | Admin Home |
| FE-07 Reload and Sign Out | Pass | Reload keeps the sign-in; Sign Out removes the token |
| FE-08 Expired sign-in | Pass | Back to login with "Your sign-in has expired. Please sign in again." |
| FE-09 Empty History | Pass | "No conversations yet…" |
| FE-10 Conversation | Pass | Two replies; the second reply saw 2 earlier messages |
| FE-11 History and Continue | Pass | Server title and "4 messages"; saved messages loaded; next reply saw 4 earlier messages |
| FE-12 Reflection | Pass | Session created; reply; listed; reopened with "Back to History" |
| FE-13 Delete | Pass | Cancel keeps the session; confirm removes it in the list and on the server |
| FE-14 No reply provider | Pass | Notice bubble; text kept; message count unchanged on the server; no safety-error screen |
| FE-15 Rate and conversation limits | Pass | Both show the server's message as a notice; text kept. Revealed D-2 (fixed) |
| FE-16 Backend stopped | Pass (after fix) | First run failed (D-3, D-4). Re-test: History and chat both show "We could not reach the server…", no old list, text kept |
| FE-17 Second account, same tab | Pass | New user sees empty History and an empty conversation |
| FE-18 Admin data | Pass | Real health status (Safety/AI "Not connected yet") and real events with times |
| FE-19 Input limits | Pass | `maxLength=2000` on all three chat inputs; username/password limits present |
| FE-20 Console | Pass | Only the expected HTTP errors from deliberate test cases; no React warnings, no uncaught errors |
| FE-21 Phone width (375 px) | Pass | Login and History fit; no sideways scrolling (see H-4) |

### 2.10 Other members' areas (limited tests)

| ID | Result | Notes |
|---|---|---|
| OT-01 Reply path with a stand-in provider | Pass | Covered by API-16/17 and FE-10/11/12 (stand-in kept outside the project) |
| OT-02 Failing provider | Pass | 503, nothing saved (BA-01) |
| OT-03 Support & Crisis Resources | Pass (partial) | Opens from the support bar; links `tel:988`, `sms:741741?body=Home`, `tel:911`; End Session returns Home. **Safety Check Unavailable: not run.** No backend response can trigger it until Emmanuel's layer sends `safety_unavailable` |
| OT-04 My Insights and admin sample cards | Pass | Render without errors (8 admin cards) |
| OT-05 Coping tools | Pass | Breathing counts down; journal "recorded for this prototype"; grounding completes; **0 backend calls**; My Insights shows the local counts |

## 3. Error log: product defects

| ID | Severity | Area (owner) | Found in | Summary | Status |
|---|---|---|---|---|---|
| D-1 | Low | Backend error messages (Akhil) | FE-04 | Invalid username shows a raw technical message | **Fixed**, re-tested |
| D-2 | Medium | Sessions + frontend integration (Akhil) | FE-15 | Empty sessions are left in History when the first message fails or a reflection is abandoned | **Fixed**, re-tested |
| D-3 | Low | Frontend integration (Akhil) | FE-16 | Backend down behind the proxy shows a generic message instead of "could not reach the server" | **Fixed**, re-tested |
| D-4 | Low | Frontend integration (Akhil) | FE-16 | A failed History reload still shows the old list under the error | **Fixed**, re-tested |
| D-5 | Low | Backend health (Akhil) | DP-02 | `/health` says "healthy" when the database tables are missing | **Fixed**, re-tested |

### 3.1 Fixes and re-test results (21 October 2026)

| ID | What changed | Re-test | Result |
|---|---|---|---|
| D-1 | `app/schemas/auth.py`: the username and password rules are checked by validators that return plain-language messages; `app/errors.py` shows such messages without the technical field prefix. The API docs still list the username pattern, and the error code stays `validation_error`. New test `test_invalid_username_gets_a_plain_message` | Browser: create account with `has space` → "Usernames are 3-32 characters: letters, numbers, dots, dashes or underscores, starting with a letter or number." Short password → "Your password must be 8-128 characters." | Pass |
| D-3 | `src/services/apiClient.js`: a 502/503/504 response **without a JSON body** (from a proxy or gateway) is treated as "could not reach the server". The backend's own 503s always have a JSON body, so they are unaffected | Backend stopped: chat notice and History both show "We could not reach the server. Check your connection and try again."; text kept. Regression: with the backend up, "no reply available" still shows "The companion can't reply right now…" | Pass |
| D-4 | `src/App.jsx`: when History (or the admin data) fails to load, the previously loaded data is cleared, so only the error shows | Backend stopped after History had loaded: History shows only the error, 0 old entries. After restart, History loads normally | Pass |
| D-5 | `app/services/health_service.py`: health also checks that the application's tables exist; Database shows "Not migrated" and `/health` answers 503 until migrations have run. `src/services/adminService.js` now shows the server's own health report on a 503 instead of a hard-coded one. New test `test_health_is_503_when_migrations_have_not_run` | Start script with `RUN_MIGRATIONS=false` on an empty database → `503`, Database "Not migrated"; with migrations → `200` healthy. Admin Architecture Health still correct | Pass |

| D-2 | Fixed only in Akhil's code; no other member's work changed. (1) `app/services/conversation_service.py`: History lists only sessions with at least one exchange; an empty session can still be opened directly. (2) `src/App.jsx` (integration code): if the first message of a new conversation fails, the app deletes the session it just created; the next attempt starts a new one. (3) `app/services/retention.py`: the cleanup job also deletes empty sessions older than 1 day (`EMPTY_SESSION_GRACE`), logged as `empty_sessions=N`. New tests `test_empty_sessions_are_not_listed`, `test_retention_removes_old_empty_sessions_only` | Browser, no reply source, on the database that still held the two empty sessions from the first run: History shows only the 3 real conversations. Two failed first messages: each session created and deleted (`201`, then `204`), no rows left, text kept. Abandoned reflection: hidden from History, removed later by the cleanup. Regression with replies: the first message keeps its session and it appears in History | Pass |

**Regression after the fixes:** backend `pytest` 82 passed; `ruff` clean; live API tests 32/32 passed (API-13 also
checks that an empty session is not listed); frontend lint clean; production build succeeds; admin dashboard health
and logs load normally.

### D-1: Invalid username shows a raw technical message (Low) — fixed
- **What happens:** the form shows `username: String should match pattern '^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$'`.
- **Steps:** Create account → username `has space` → valid password → submit.
- **Expected:** a plain message such as "Usernames are 3-32 letters, numbers, dots, dashes or underscores."
- **Suggested fix:** give the username and password rules friendly validation messages in the backend, and/or add a
  matching `pattern` with a `title` on the username input.

### D-2: Empty sessions are left in History (Medium) — fixed
- **What happens:** a conversation session is created just before the first message is sent. If that message fails
  and the user leaves, an empty "Conversation · 0 messages" entry stays in History. Today the first message always
  fails, because no replies are available yet. "Use This Prompt" creates a reflection session immediately, so leaving
  without writing leaves "Reflection: … · 0 messages" as well.
- **Steps:** Start a Conversation → send a message while no reply is available → Back → History.
- **Expected:** no empty entries in History.
- **Suggested fix:** delete the new session when its first message fails (or create it only after a successful first
  message), and hide sessions with 0 messages from History or clean them up on the server.

### D-3: Backend down shows a generic message (Low) — fixed
- **What happens:** with the backend down behind the Vite proxy (or a gateway), the proxy answers `502` with no JSON
  body, and the app shows "Something went wrong. Please try again."
- **Steps:** stop the backend → send a message or open History.
- **Expected:** "We could not reach the server. Check your connection and try again."
- **Suggested fix:** in `apiClient.js`, treat `502`/`503`/`504` responses without a `{code, detail}` body as a network
  error.

### D-4: Failed History reload shows the old list (Low) — fixed
- **What happens:** the load error appears **above the previously loaded list**, so stale data looks current, and
  its buttons stay active.
- **Steps:** open History → stop the backend → Back → open History again.
- **Expected:** only the error (or an empty list) after a failed load.
- **Suggested fix:** clear `conversationSessions` (or hide the list) when the History load fails.

### D-5: `/health` ignores a missing schema (Low) — fixed
- **What happens:** `/health` reports "healthy" even when the database has no tables (migrations not run), because it
  only checks the connection (`SELECT 1`).
- **Steps:** start with `RUN_MIGRATIONS=false` on an empty database → `GET /health`.
- **Expected:** "unhealthy" (`503`) until the schema exists, so a load balancer does not send traffic too early.
- **Suggested fix:** also check that `alembic_version` holds the head revision before reporting healthy.

**Previously found and fixed (regression-checked in this run):** duplicate React keys when saved and new messages
were mixed in one chat (found during integration; fixed). FE-20 confirms no key warnings.

## 4. Error log: test-script errors (not product defects)

| ID | Found in | What happened | Resolution |
|---|---|---|---|
| H-1 | API-20 | The rate-limit test reused a scenario where a session holds only 4 messages, so its 3rd message hit the **conversation** limit, not the rate limit. A separate check confirmed the app is correct: exactly 5 messages per minute are allowed, and refused "conversation limit" messages do not use up rate-limit quota | Test changed to use a new session per message; re-run: Pass |
| H-2 | DP-02, DP-04 | The harness's stop helper looked for `127.0.0.1:8012`, but the start script binds `0.0.0.0:8012`, so an earlier server kept answering. DP-04 then wrongly showed the API docs enabled in production | Stale server stopped; helper fixed; both re-run on a clean port: Pass |
| H-3 | OT checks | A browser script opened the newest History entry, a reflection, and looked for the Continue Session input | Script corrected to open a conversation entry |
| H-4 | FE-21 | A phone-width screenshot taken during the viewport change looked clipped | Measured: every element fits within 375 px and there is no horizontal scroll. Not a defect |

## 5. Not run, and how to run them

### DB-06: MySQL 8
- **Reason:** the only MySQL database on this machine belongs to the newer project, and its credentials are in a real
  configuration file. The test suite drops and recreates tables, so it must only run against an empty, throwaway
  database.
- **How to run:** create an empty database (for example `wellness_test`), then in `backend/`:

```bash
TEST_DATABASE_URL=mysql+pymysql://<user>:<pass>@localhost:3306/wellness_test python -m pytest -q
```

### DP-05: Docker image build
- **Reason:** Docker is not installed on this machine.
- **How to run:**

```bash
docker build -t wellness-backend backend/
docker run --env-file backend/.env -p 8000:8000 wellness-backend
```

Then open http://127.0.0.1:8000/health.

### OT-03 (part): Safety Check Unavailable trigger
- **Reason:** needs Emmanuel's safety layer.
- **How to run:** re-test after his reply provider can raise `safety_unavailable`.

## 6. Recommendation

The work is ready for review and for the team to build on. Before the demo:

1. All five defects (D-1 to D-5) are **fixed and re-tested** (section 3.1).
2. Retention note: empty sessions are removed by the cleanup job, which runs only when `RETENTION_DAYS` > 0 (default 30).
3. Run **DB-06** on a throwaway MySQL database and **DP-05** where Docker is available.
4. Re-run FE-10 to FE-16 once Emmanuel's reply provider is connected, and OT-03 once `safety_unavailable` exists.
