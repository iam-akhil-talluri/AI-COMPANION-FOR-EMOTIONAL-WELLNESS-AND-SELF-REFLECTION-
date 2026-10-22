# Frontend–Backend Integration Review: What Is Missing

From: Akhil (backend, database, sessions and conversation memory, logging, deployment support)

Scope: the frontend in `src/` (as it is on the `CynthiaL_Frontend` branch) checked against the backend in `backend/`.
Line numbers refer to the current `src/App.jsx`.

## 1. Summary

**The frontend is not connected to the backend at all.** It makes no network requests: there is no `fetch`, no API
client, no `/api` path and no sign-in token anywhere in `src/`. Every screen still runs on React state, hard-coded
sample data, or the mock in `src/services/chatService.js`. The only browser storage used is a local visit counter in
`localStorage`.

| Area | Backend ready? | Frontend connected? | Who unblocks it |
|---|---|---|---|
| Sign in, create account, sign out | Yes | **No** | Cynthia |
| Conversation sessions and history | Yes | **No** | Cynthia |
| Sending messages | Endpoint ready, but no replies yet (always `503`) | **No** | Cynthia (wiring), Emmanuel (replies) |
| Reflection sessions | Yes | **No** | Cynthia |
| Continue a previous session | Yes | **No** | Cynthia |
| Delete a session | Yes | **No** (no button) | Cynthia |
| Admin: Recent Log Events | Yes | **No** | Cynthia |
| Admin: Architecture Health | Partly (3 of 6 rows) | **No** | Cynthia; Emmanuel for the Safety and AI rows |
| Support / crisis routing after a message | **No** | Uses a mock status | Emmanuel, then Akhil (API), then Cynthia |
| My Insights | **No endpoint** | Sample data | Korey, then Cynthia |
| Admin statistics, safety decisions, escalations, AI cost | **No endpoint** | Sample data | Korey / Emmanuel, then Cynthia |
| Journal save, coping-tool counts | **No endpoint** | Local state only | Not assigned yet (team decision) |

Severity used below: **P1** = blocks a working end-to-end demo, **P2** = wrong behaviour or data once connected,
**P3** = polish or outdated text.

## 2. Setup and plumbing (nothing exists yet)

| # | Missing | Where | Severity |
|---|---|---|---|
| S1 | **Vite dev proxy** for `/api` → `http://127.0.0.1:8000`. Without it, browser calls go to the Vite server and get 404 | `vite.config.js` has only `plugins: [react()]` | P1 |
| S2 | **API base URL for production** (`VITE_API_URL`) and a root `.env.example` documenting it | No `.env*` file in the repo root | P2 |
| S3 | **Shared API client** that adds `Authorization: Bearer <token>`, sends JSON, applies a timeout, and turns `{code, detail}` errors into one error type | No such module in `src/services/` | P1 |
| S4 | **Token storage** (recommended: `sessionStorage`) and clearing it on sign-out or any `401` | None | P1 |
| S5 | **Restore sign-in on page load** with `GET /api/auth/me`. Today every reload drops the user back to the login screen and loses everything | `currentScreen` starts as `'login'` (line 197) | P2 |
| S6 | **Replace the mock** `src/services/chatService.js`: it waits 500 ms and matches keywords such as "recipe" and "stressed" | Imported at line 81 | P1 |
| S7 | **Remove the `localStorage` visit and conversation counters.** They are local only, never reach the backend, and duplicate the backend event log | Lines 60-79, 242-257, and `recordNewConversation()` at 783 | P3 |

## 3. Screen by screen

### 3.1 Login (lines 400-488)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| L1 | Login is fake: any username and password work, and the username "admin" plus the checkbox makes you an administrator. Needs `POST /api/auth/login` with `{username, password, admin}` and the role from the response | 419-443 | P1 |
| L2 | No way to **create an account** (`POST /api/auth/register`). Without it nobody except a script-created admin can sign in | — | P1 |
| L3 | Server errors not shown: `401 invalid_credentials`, `403 admin_required`, `409 username_taken`, `422 validation_error`, `429 rate_limited` (show `detail`) | 472-474 handles only the local check | P1 |
| L4 | No "busy" state on the button while the request runs (double submits) | 476 | P3 |
| L5 | `autoComplete` attributes are commented out (`username`, `current-password` / `new-password`) | 449, 456 | P3 |
| L6 | Placeholder note "Prototype Placeholder login … to be connected to backend(?)" should become the "don't use your real name or email" hint | 480-482 | P3 |
| L7 | No input limits matching the backend: username 3-32 characters (letters, numbers, `.`, `_`, `-`), password 8-128 characters | 446-457 | P3 |

### 3.2 Home and Sign Out (lines 491-704)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| H1 | **Sign Out does not call `POST /api/auth/logout`** and does not clear a token | 517-524 (user), 646-651 (admin) | P1 |
| H2 | **Sign Out does not clear the user's data.** History (`conversationSessions`), reflection and continue-session messages, `selectedSession` and `activeConversationId` all survive. With real accounts, the next person to sign in on the same tab would see the previous user's conversations. The admin Sign Out clears even less | 517-524, 646-651 | P1 |
| H3 | The welcome line could show the signed-in `username` | 509-511 | P3 |
| H4 | "Start a Conversation" re-opens whatever was left in `messages`. With the backend it should start a fresh session (clear `messages` and `activeConversationId`) | 548 | P2 |

### 3.3 Conversation (lines 706-918)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| C1 | **No session is created on the server.** The first message creates a local session with `id: Date.now()`. Needs `POST /api/sessions` (`type: "conversation"`), keeping the returned UUID `id` | 782-808 | P1 |
| C2 | **Message is not sent to the backend.** Needs `POST /api/sessions/{id}/messages` with `{content}` | 843 | P1 |
| C3 | Reads `response.message`; the backend returns the reply in **`response.response`** | 866 | P1 |
| C4 | Branches on `status === 'concern'` and `'error'`. The backend returns `status: "ok"` only, and reports failures as HTTP errors (see section 5) | 848-856 | P1 |
| C5 | **Every failure opens the "Safety Check Unavailable" screen**, including "AI unavailable" (`503 reply_unavailable`), rate limits, too-long messages, an expired sign-in and network errors. Most of these should show `detail` in the conversation and keep the user's text | 875-881 | P1 |
| C6 | On failure the user's message stays on screen, but the backend saved nothing. After a reload it disappears. Remove it (or mark it as not sent) and put the text back in the input | 819-834, 875-881 | P2 |
| C7 | Title is built locally (first 40 characters); the backend builds its own from the first six words. Use the server's title | 796-798 | P3 |
| C8 | No `maxLength={2000}` on the input (backend limit: 2,000 characters) | 892-899 | P3 |
| C9 | The opening greeting is hard-coded. Send it as the session `prompt` so History shows the same text | 738, 799 | P3 |

### 3.4 Reflection Prompt (lines 921-1012)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| R1 | **"Use This Prompt" only creates a local session.** Needs `POST /api/sessions` with `{type: "reflection", prompt, title: "Reflection: <prompt>"}` and the returned `id` | 950-981 | P1 |
| R2 | No busy state or error message if creating the session fails | 948-984 | P2 |

### 3.5 Reflection Chat (lines 1016-1188)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| RC1 | Messages are not sent to `POST /api/sessions/{selectedSession.id}/messages`; same issues as C2-C6 | 1083-1152 | P1 |
| RC2 | "Back to Reflection" always goes to the prompt screen, even when the chat was opened from History | 1026 | P3 |
| RC3 | No `maxLength` on the input | 1161-1170 | P3 |

### 3.6 Conversation History (lines 1452-1514)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| HI1 | **Shows three hard-coded sample sessions.** Needs `GET /api/sessions` each time the screen opens | 307-362, 1472 | P1 |
| HI2 | **"Continue" uses messages kept in React state.** Needs `GET /api/sessions/{id}` to load the saved messages (they are not included in the list response) | 1485-1501 | P1 |
| HI3 | No loading, empty ("No conversations yet") or error states | 1469-1510 | P2 |
| HI4 | Field names differ: `session.date` (backend gives `created_at` / `last_active` ISO dates, which need formatting), `messageCount` (backend: `message_count`). See section 4 | 1476, 1479 | P1 |
| HI5 | **No delete button**, although `DELETE /api/sessions/{id}` exists and the privacy design lets users delete sessions | — | P2 |
| HI6 | "1 messages" plural | 1479 | P3 |

### 3.7 Continue Session (lines 2390-2599)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| CS1 | Messages are not sent to `POST /api/sessions/{id}/messages`; same issues as C2-C6 | 2490-2563 | P1 |
| CS2 | The placeholder comment says the real messages still need loading (`GET /api/sessions/{id}`); see HI2 | 2426-2432 | P1 |
| CS3 | No `maxLength` on the input | 2572-2581 | P3 |

### 3.8 Coping Tools (lines 1191-1450)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| CT1 | Journal "Save" only clears the box and says "Reflection recorded for this prototype". Nothing is stored | 1355-1386 | Blocked: no backend endpoint |
| CT2 | Breathing and grounding completions are counted only in React state (`copingUsage`), lost on reload, and per tab | 295-306, 1332, 1436 | Blocked: no backend endpoint |

The exercises themselves are static content and need no backend. The team has to decide who owns journal and
coping-usage storage before this can be connected.

### 3.9 My Insights (lines 1515-1810)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| MI1 | Built from `SAMPLE_ANALYTICS` plus the local `copingUsage` counts. There is **no `GET /api/analytics/me` in this backend** | 84-108, 1521-1538 | Blocked (Korey) |

Keep the sample data until the analytics endpoint exists. Consider labelling the screen as sample data so nobody
mistakes it for real activity in the demo.

### 3.10 Admin Dashboard (lines 1811-2385)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| AD1 | **Recent Log Events** use sample rows. `GET /api/admin/logs` exists and returns `time`, `type`, `message` and `status` with the same meaning. `time` is an ISO date and must be formatted (the sample uses `"10:42 AM"`) | 2327-2357 | P1 |
| AD2 | **Architecture Health** uses sample rows. `GET /api/health` gives real status for "Backend / API", "Database" and "Logging". "Frontend" can be added by the page. "Safety / Moderation" and "AI Service" have no source yet | 2289-2306 | P2 (partly blocked) |
| AD3 | Overview, Session Frequency, Escalations, Safety Decisions, Coping Tool Activity and Cost & AI Usage: **no endpoint** | 1857-2275 | Blocked (Korey / Emmanuel) |
| AD4 | The admin screen opens only because the fake login set `userRole`. After L1 the role must come from the server. The backend refuses `/api/admin/*` for non-admins on its own | 1820 | P1 (part of L1) |
| AD5 | A non-admin who somehow reaches `currentScreen === 'admin'` gets the unrelated "This screen will be built next" placeholder | 2757-2781 | P3 |

### 3.11 Support & Crisis Resources (lines 2605-2672)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| SR1 | Opened after a message only when the mock returns `concern`. The backend has **no crisis or support status yet**. The screen is still reachable from the support bar, which is correct and needs no backend | 848, 1116, 2527 | Blocked (Emmanuel) |
| SR2 | "End Session" clears `messages` but not `activeConversationId`, or the reflection and continue-session state. After integration, the next message could be sent into the old session | 2659-2665 | P2 |

### 3.12 Safety Check Unavailable (lines 2680-2753)

| # | Missing / wrong | Lines | Severity |
|---|---|---|---|
| SE1 | Should open only for a real safety-check failure (`503 safety_unavailable`, once Emmanuel's layer exists), not for every error (see C5) | — | P1 (with C5) |
| SE2 | "Try Again" always goes to the Conversation screen, even when the error happened in Reflection Chat or Continue Session; it should return to the previous screen | 2718 | P2 |
| SE3 | Unsent text is lost; "Try Again" should restore it to the input | 2715-2721 | P3 |

## 4. Data shape mismatches

| Frontend expects today | Backend actually sends | Fix in frontend |
|---|---|---|
| Session `id`: number (`Date.now()`) | UUID string | Treat ids as strings |
| `session.date`: preformatted string | `created_at`, `last_active` (ISO, UTC, ending in `Z`) | Format with `toLocaleDateString` |
| `session.messageCount` | `message_count` | Rename when mapping |
| `session.messages` inside the list | Not in the list; only in `GET /api/sessions/{id}` | Load on "Continue" |
| Message `{role, text}` | `{id, role, content, created_at}` | Map `content` → `text` |
| Reply `{status, message}` | `{session_id, status: "ok", response, created_at}` | Read `response` |
| `status`: `clear` / `concern` / `error` | `ok` only; failures are HTTP errors | Use the HTTP status and `code` |
| Role chosen by the checkbox | `user.role` from login, register or `/me` | Use the server's role |
| Title: first 40 characters (frontend) | First 6 words (conversation, set by the server); the given title (reflection) | Show the server's title; `null` → "Conversation" |

## 5. Error handling that is missing

Every backend error has the shape `{"code": "...", "detail": "..."}`, and `detail` is safe to show to the user. None of
these are handled today:

| Code (HTTP) | When | What the frontend should do |
|---|---|---|
| `not_authenticated` / `session_expired` (401) | No token, expired token, signed out elsewhere | Clear the token and user data; go to login with the message |
| `invalid_credentials` (401), `admin_required` (403), `username_taken` (409) | Login / register | Show `detail` on the login form |
| `validation_error` (422) | Bad username/password format, bad session type | Show `detail` |
| `empty_message` / `message_too_long` (422) | Blank, or more than 2,000 characters | Show `detail`; keep the text |
| `rate_limited` (429) | Too many messages or sign-in attempts | Show `detail`; respect `Retry-After` |
| `conversation_limit` (429) | 100 messages in a session | Suggest a new conversation |
| `reply_unavailable` (503) | No reply available (always, until Emmanuel's layer is connected) | Show a notice in the chat; keep the text; **not** the safety-error screen |
| `not_found` (404) | Session deleted, purged or not this user's | Return to History and refresh it |
| `payload_too_large` (413), `internal_error` (500), `database_unavailable` (503) | Server problems | Show `detail` |
| Network error or timeout | Backend not running or unreachable | Show "Can't reach the server"; keep the text |

## 6. Missing on the backend side (not the frontend's fault)

| Missing | Effect on the frontend | Owner |
|---|---|---|
| **Reply provider** (safety and AI) | Every message returns `503 reply_unavailable`; no conversation can get a reply | Emmanuel |
| `support` / `crisis` status and `resources` in the message response | Crisis routing after a message can't work | Emmanuel + Akhil |
| `safety_unavailable` error | The Safety Check Unavailable screen has no real trigger | Emmanuel |
| `GET /api/analytics/me` | My Insights stays on sample data | Korey |
| Admin statistics, safety events, escalations, AI cost endpoints | Most admin cards stay on sample data | Korey / Emmanuel |
| Journal and coping-usage endpoints | Journal and tool counts are not saved | Team decision |
| "Safety / Moderation" and "AI Service" in `/api/health` | Two Architecture Health rows have no source | Emmanuel |

## 7. Outdated text and comments in the frontend

| Where | Says | Should say |
|---|---|---|
| Integration map at the top of `App.jsx` (line 40) | "PostgreSQL stores sessions and messages" | MySQL |
| Integration map (lines 19, 35) | `/sessions`, `/sessions/{session_id}` | `/api/sessions`, `/api/sessions/{id}` |
| Line 84 and others | `GET /analytics/me` | `/api/analytics/me` (once it exists) |
| Footers (lines 911, 1181, 2592) | "will be / should be screened…" | Accurate only after the safety layer is connected. Until then, messages get no reply at all, so nothing reaches an AI unscreened |
| Line 224 | `'What would you like to talk about today'` (missing "?") | Add the question mark |
| Line 1384 | "Reflection recorded for this prototype" | Update once journal saving exists |

## 8. Recommended order of work

1. **Plumbing:** Vite proxy (S1), API client and token handling (S3, S4).
2. **Accounts:** real sign-in and create account (L1-L3), sign-out that calls the server and clears all user data (H1, H2), restore on reload (S5).
3. **Sessions:** create on first message or "Use This Prompt" (C1, R1); History from `GET /api/sessions` (HI1, HI4); Continue loads `GET /api/sessions/{id}` (HI2).
4. **Messages:** send through the backend in all three chat screens (C2-C4, RC1, CS1) with the error handling in section 5 (C5, C6). Expect `503 reply_unavailable` until Emmanuel connects replies.
5. **Admin:** Recent Log Events from `/api/admin/logs` (AD1) and the health rows from `/api/health` (AD2).
6. **Polish:** delete button (HI5), loading and empty states (HI3), input limits, wording (section 7).
7. **Later**, as endpoints appear: crisis and support routing, My Insights, admin statistics, journal and coping usage.

The backend side of steps 1-5 is ready and covered by 78 passing tests. `backend/docs/handoff-cynthia.md` has every
request and response shape.
