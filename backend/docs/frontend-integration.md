# Frontend–Backend Integration: What Is Connected

From: Akhil (backend, database, sessions and conversation memory, logging, deployment support)

This document records how the React frontend (`src/`) is now connected to the FastAPI backend (`backend/`), what was
changed, how each piece was verified, and what is deliberately **not** connected because it belongs to another
teammate. It closes the setup, account, session, messaging and admin-log gaps listed in
`frontend-integration-gaps.md`.

> **Note for Cynthia:** this work changed frontend files (`App.jsx`, `App.css`, `vite.config.js` and
> `src/services/`). The screens, layout and existing styles are unchanged apart from the items listed in section 3.
> Please review the new wording and styles.

## 1. Summary

| Feature | Status | Backend endpoint(s) |
|---|---|---|
| Create account | **Connected** | `POST /api/auth/register` |
| Sign in (user and administrator) | **Connected** | `POST /api/auth/login` |
| Stay signed in after a page reload | **Connected** | `GET /api/auth/me` |
| Sign out (also clears the user's data from the screen) | **Connected** | `POST /api/auth/logout` |
| Expired sign-in returns to the login screen | **Connected** | any `401` |
| Start a conversation (session created on the first message) | **Connected** | `POST /api/sessions` |
| Reflection prompt → reflection session | **Connected** | `POST /api/sessions` |
| Send messages (Conversation, Reflection Chat, Continue Session) | **Connected** | `POST /api/sessions/{id}/messages` |
| Conversation History list | **Connected** | `GET /api/sessions` |
| Continue a saved session (loads its messages) | **Connected** | `GET /api/sessions/{id}` |
| Delete a session | **Connected** | `DELETE /api/sessions/{id}` |
| Admin: Recent Log Events | **Connected** | `GET /api/admin/logs` |
| Admin: Architecture Health (all six layers) | **Connected** | `GET /api/health` |
| AI replies and safety screening (support resources, crisis routing, Safety Check Unavailable) | **Connected** | `POST /api/sessions/{id}/messages` (see `ai-and-safety.md`) |
| Admin: Overview, Session Frequency, Escalations, Safety Decisions, Cost & AI Usage (with token and cost charts) | **Connected** | `GET /api/admin/analytics` |
| My Insights, admin Coping Tool Activity | Not connected: no endpoint (Korey) | — |
| Journal save, coping-tool counts | Not connected: no endpoint | — |

**Update (safety and AI layer connected):** replies now come from the companion pipeline. `support` replies show
support resource cards under the reply, `crisis` replies open the Support & Crisis Resources screen (with a "Back to
Conversation" button), and `503 safety_unavailable` opens the Safety Check Unavailable screen, whose "Try Again"
returns to the screen the message came from with the text restored. Sections below that describe the state before
this are kept for history.

## 2. Files changed

| File | Change |
|---|---|
| `vite.config.js` | Dev proxy: `/api` → `http://127.0.0.1:8000` (override with `VITE_DEV_API_TARGET`) |
| `.env.example` (new, repo root) | Documents `VITE_API_URL` for production builds |
| `src/services/apiClient.js` (new) | One place for every request: base URL, `Authorization: Bearer` token, 30-second timeout, `{code, detail}` errors → `ApiError`, `401` handling |
| `src/services/authService.js` (new) | `signIn`, `register`, `restoreSession`, `signOut` |
| `src/services/chatService.js` (rewritten) | The keyword mock is replaced with `createSession`, `listSessions`, `getSession`, `deleteSession` and `sendMessageToBackend` |
| `src/services/adminService.js` (new) | `getRecentLogs`, `getHealth`, `formatLogTime` |
| `src/App.jsx` | Screens wired to the services (section 3); the `localStorage` visit counters and the three hard-coded sample sessions are removed |
| `src/App.css` | New section "ACCOUNTS, STATUS AND NOTICES": login switch link, form hint, status text, notice bubble, Delete button, disabled buttons |
| `.gitignore` | Ignores `.env` and `.env.*` (keeps `.env.example`) |

Backend code was **not** changed for this work.

## 3. Screen by screen

### Login
- The fake login (any password; username "admin" = administrator) is replaced by the real calls.
- The **"Sign in as Administrator"** box sends `admin: true`. A non-admin account gets the server's `403`, shown as
  "Administrator sign-in was not successful". The role always comes from the server.
- **New:** a "Create an account" / "Sign in" switch. In create mode it adds a hint ("3-32 letters, numbers… please
  don't use your real name or email") and the input limits that match the backend (username 3-32 characters,
  password 8-128 characters).
- The button shows "Please wait..." during the request, and server errors (`detail`) appear under the form.
- **New:** a "Loading..." screen while a saved sign-in is checked on page load.
- The placeholder note "Prototype Placeholder login…" is replaced by "No email or real name is needed…".

### Home
- The welcome line shows the username: "Welcome, calm-river!".
- **Sign Out** (user and admin) calls the backend and clears the token and **all** user data held on the screen
  (history, open chats, admin data), so the next person on the same browser tab sees nothing of the previous user.
- **Start a Conversation** always starts a fresh conversation. Earlier ones stay in History.

### Conversation
- The first message creates the session on the server. After that, every message is sent to it.
- One shared function, `deliverMessage()`, now handles sending for all three chat screens (it replaces three copies
  of the mock logic):
  - **Success:** the reply appears.
  - **Any failure:** a **Notice** bubble shows the server's message, nothing is saved, and the text is put back in
    the input. This covers no reply available, rate limit, too-long message and network errors.
- Message inputs are limited to 2,000 characters (the backend limit).

### Reflection Prompt and Reflection Chat
- **"Use This Prompt"** creates a reflection session on the server (`prompt` plus title `Reflection: <prompt>`).
  The button shows "Starting...", and an error message appears if the session can't be created.
- Messages go through the same `deliverMessage()`.
- When a reflection is opened from History, the back button says **"Back to History"** and returns there.

### Conversation History
- The list comes from the backend every time the screen opens, newest activity first. It has loading, empty ("No
  conversations yet…") and error states.
- **Continue** loads the saved messages from the server (the button shows "Opening...").
- **New: Delete** removes the session after a confirmation. It uses the existing `DELETE /api/sessions/{id}`.
- "1 message" / "2 messages" now uses the correct singular or plural.

### Continue Session
- Shows the messages loaded from the server. New messages go through `deliverMessage()`.

### Admin Dashboard
- **Recent Log Events:** the 10 newest events from `GET /api/admin/logs`, with readable times (for example
  "9:42 PM"). Warning and error events keep their existing highlight.
- **Architecture Health:**
  - Frontend: this page loaded, so it is healthy.
  - Backend / API, Database and Logging: from `GET /api/health`.
  - Safety / Moderation and AI Service: shown as **"Not connected yet"** until Emmanuel's layer exists.
- All other cards keep their sample data (see section 6).

### Support & Crisis Resources and Safety Check Unavailable
- Content and buttons are unchanged (Emmanuel's area).
- "End Session" on both screens now also forgets the current server session, so the next conversation starts a new one.
- No backend response opens these screens automatically today. The support bar still opens the support page at any
  time.

## 4. Error handling

All errors come from the backend as `{code, detail}`; `detail` is shown to the user as it is.

| Situation | What the user sees |
|---|---|
| Wrong username or password | Message under the login form |
| Admin box ticked on a non-admin account | "Administrator sign-in was not successful" |
| Username already taken / invalid / too many attempts | The server's message under the form |
| Sign-in expired or revoked (any `401`) | Back to the login screen with "Your sign-in has expired. Please sign in again." |
| No reply available (`503 reply_unavailable`) | Notice bubble in the chat; text kept in the input; nothing saved |
| Too long, rate limited, conversation limit | Notice bubble with the server's message; text kept |
| Backend not running or unreachable | "We could not reach the server. Check your connection and try again." |
| History, Continue or Delete fails | Error message on the History screen |
| Admin data fails to load | Error message in the Recent Log Events card |

## 5. How it was verified

**Test setup:** a local backend (SQLite database, a test admin account) and the Vite dev server, driven in a real
browser.

**Stand-in replies:** to test the message flow before Emmanuel's layer exists, the backend was first run with a
**stand-in reply source**. It was kept only in a scratch folder and labelled "[test reply]", and it is **not** in the
project. The backend was then run without it, to test the real current behaviour.

| Check | Result |
|---|---|
| `/api` requests from the Vite server reach the backend (proxy) | Pass |
| Create account → Home shows "Welcome, calm-river!" | Pass (`201`) |
| Page reload keeps the user signed in | Pass |
| Sign Out → login screen, token removed | Pass (`204`) |
| Wrong password → error message | Pass (`401`) |
| Non-admin with the Administrator box → refused | Pass (`403`) |
| Admin sign-in → Admin Home | Pass |
| New user's History → "No conversations yet" (sample sessions gone) | Pass |
| Conversation: 2 messages saved; second reply saw the 2 earlier messages (memory) | Pass |
| History shows the conversation with the server title and "4 messages" | Pass |
| Continue → saved messages loaded; new reply saw all 4 earlier messages | Pass |
| Reflection → session created; reply received; listed in History | Pass |
| Reflection opened from History → "Back to History" | Pass |
| Delete → removed from the list and from the server | Pass |
| No reply source → Notice bubble, text restored, message count unchanged on the server | Pass |
| Invalid / expired token → login screen with "Your sign-in has expired…" | Pass |
| Second account on the same tab sees none of the first user's data | Pass |
| Admin: Recent Log Events show real events; Architecture Health shows real status | Pass |
| A duplicate-key React warning (saved and new messages shared keys) was found during testing and fixed | Fixed and re-checked |
| `npm run lint` (oxlint) | 0 warnings, 0 errors |
| `npm run build` | Succeeds |
| Backend `pytest` | 78 passed |

## 6. Not connected (other owners or no endpoint yet)

| Item | Why | Owner |
|---|---|---|
| AI replies and safety screening | The backend's reply provider is not registered yet; messages return `503` until it is | Emmanuel |
| Crisis / support routing after a message | Needs `support` / `crisis` statuses in the API | Emmanuel (+ Akhil for the API) |
| "Safety Check Unavailable" triggered by the backend | Needs a `safety_unavailable` error from the safety layer | Emmanuel |
| My Insights | No `GET /api/analytics/me` | Korey |
| Admin Overview, Session Frequency, Escalations, Safety Decisions, Coping Tool Activity, Cost & AI Usage | No endpoints | Korey / Emmanuel |
| Journal save and coping-tool counts | No endpoints; counts stay in the browser tab and reset on sign-out | Team decision |

These screens keep the existing sample data and behaviour, unchanged.

## 7. Running it locally

1. **Backend:** follow `backend/README.md`, then run `python -m uvicorn app.main:app --reload` in `backend/`.
2. **Frontend:** in the repo root, run `npm ci` once, then `npm run dev`, and open http://localhost:5173.
3. **Create an account** from the login screen.
4. **For an administrator,** run `python -m scripts.create_admin --username <name>` in `backend/`, then sign in with
   the Administrator box ticked.

For production, build the frontend with `VITE_API_URL` set to the deployed backend URL, and add the frontend's URL to
the backend's `CORS_ORIGINS`.
