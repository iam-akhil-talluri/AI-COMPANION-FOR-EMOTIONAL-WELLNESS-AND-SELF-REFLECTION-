# Handoff for Cynthia: connecting the frontend to the backend

From: Akhil (backend, database, sessions and conversation memory, logging, deployment support)

The backend in `backend/` now provides real sign-in, sessions, conversation history and an operational log. This
document lists every endpoint the frontend can use today, the exact request and response shapes, the errors to
handle, and which screens still have to keep their sample data. **No frontend files were changed.** All frontend work
is yours.

## 1. Running the backend locally

Follow [`backend/README.md`](../README.md) (Python 3.12+, MySQL 8). Then:

```powershell
cd backend
python -m uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000, with interactive docs at http://127.0.0.1:8000/docs (you can try every call there)
- Health: http://127.0.0.1:8000/health

### Reaching the API from Vite

The simplest option is a dev proxy in `vite.config.js`. All `/api` calls then go to the backend, and no CORS setup
is needed:

```js
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  }
})
```

Without the proxy, call the backend's full URL. Your origin must then be listed in the backend's `CORS_ORIGINS`
setting (default `http://localhost:5173`). For production, use a `VITE_API_URL` variable that holds the deployed
backend URL.

## 2. General rules

- **Sign-in token:** login and register return a `token`. Send it on every other request as
  `Authorization: Bearer <token>`. A token lasts 8 hours. Store it in `sessionStorage` (cleared when the tab closes)
  rather than `localStorage`.
- **JSON** in and out, with `Content-Type: application/json`.
- **Dates** are UTC ISO strings ending in `Z` (`"2026-10-21T20:30:00.123456Z"`). Format them in the browser, for
  example with `new Date(value).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })`.
- **Errors** always look like `{"code": "...", "detail": "..."}`. `detail` is written for users and **safe to show
  as it is**. Branch on `code`, never on the wording.
- **Any `401`** (`not_authenticated` or `session_expired`) means the sign-in is gone: clear the token and go back
  to the login screen.

## 3. Accounts

| Action | Request | Success |
|---|---|---|
| Create account | `POST /api/auth/register` `{ "username", "password" }` | `201` `{ token, token_type, expires_in, user }` |
| Sign in | `POST /api/auth/login` `{ "username", "password", "admin": false }` | `200` same shape |
| Who am I | `GET /api/auth/me` (with token) | `200` `{ "username", "role" }` |
| Sign out | `POST /api/auth/logout` (with token) | `204`, and every token for that account stops working |

`user` is `{ "username": "calm-river", "role": "user" }`, where `role` is `"user"` or `"admin"`.

- **"Sign in as Administrator" checkbox:** send `"admin": true`. If the account is not an admin, the server answers
  `403 admin_required` with the same wording the screen already uses ("Administrator sign-in was not successful").
  Use the returned `role` to decide whether to show the Admin Dashboard. The server checks the role again on every
  admin request.
- **Account rules:**
  - Usernames are 3-32 characters (letters, numbers, `.`, `_`, `-`, starting with a letter or number) and are not
    case-sensitive.
  - Passwords are 8-128 characters.
  - Please add a hint not to use a real name or email address. Accounts are pseudonymous.
- **Restoring a sign-in on page load:** if a token is stored, call `GET /api/auth/me`. A `200` means the user is
  still signed in; a `401` means show the login screen.

| Error | When |
|---|---|
| `401 invalid_credentials` | Wrong username or password (the same message for both) |
| `403 admin_required` | Admin checkbox with a non-admin account |
| `409 username_taken` | Register with an existing username |
| `422 validation_error` | Username or password doesn't meet the rules |
| `429 rate_limited` | Too many failed sign-ins (5 per account per 15 minutes) or too many new accounts |
| `403 registration_disabled` | New accounts are switched off on the server |

The old login screen accepts any username and password, and treats the username "admin" as an administrator. That
check needs to be replaced with the calls above.

## 4. Sessions and history

| Action | Request | Success |
|---|---|---|
| Start a session | `POST /api/sessions` `{ "type": "conversation" \| "reflection", "prompt"?, "title"? }` | `201` session summary |
| History list | `GET /api/sessions?limit=100` | `200` list of summaries, most recently active first |
| Open one session | `GET /api/sessions/{id}` | `200` summary plus `messages` |
| Delete a session | `DELETE /api/sessions/{id}` | `204` |

Session summary:

```json
{
  "id": "c1a0d008-972c-4d14-8a73-446c652a56cf",
  "type": "conversation",
  "title": "Work has been really stressful this...",
  "prompt": "What would you like to talk about today?",
  "created_at": "2026-10-21T20:30:00Z",
  "last_active": "2026-10-21T20:35:00Z",
  "message_count": 4
}
```

`messages` (in `GET /api/sessions/{id}`) is oldest first:

```json
[
  { "id": 1, "role": "user", "content": "I had a long day.", "created_at": "…Z" },
  { "id": 2, "role": "assistant", "content": "That sounds tiring…", "created_at": "…Z" }
]
```

Notes:

- The API uses `content`; the screens use `text`. Convert when you load messages.
- **Title:**
  - A new conversation has `title: null` until the first message is sent. The backend then sets it from the first
    six words.
  - For a **reflection**, send the title yourself (for example `"Reflection: <prompt>"`). The backend keeps it.
  - A session with `title: null` can be shown as "Conversation".
- **Who sees what:** users only ever see their own sessions. Someone else's session ID answers `404 not_found`, the
  same as an ID that doesn't exist.
- **Old sessions:** text older than 30 days is deleted automatically, and those sessions disappear from the list.
- **Suggested flow:**
  - **Start a Conversation:** create the session when the first message is sent, keep its `id`, then send messages
    to it.
  - **Use This Prompt (Reflection):** create a `reflection` session with `prompt` and `title`.
  - **History → Continue:** call `GET /api/sessions/{id}` and show `messages`.

## 5. Sending a message

`POST /api/sessions/{id}/messages` with `{ "content": "…" }`

Success (`200`):

```json
{ "session_id": "…", "status": "ok", "response": "the companion's reply", "created_at": "…Z" }
```

| Error | When | Suggested UI |
|---|---|---|
| `422 empty_message` / `message_too_long` | Blank, or more than 2,000 characters | Show `detail`, keep the text in the input (add `maxLength={2000}` to the inputs) |
| `429 rate_limited` | More than 10 messages a minute or 120 an hour | Show `detail`; a `Retry-After` header says how many seconds to wait |
| `429 conversation_limit` | 100 messages in one session | Show `detail` and suggest starting a new conversation |
| `503 reply_unavailable` | No reply available (see below) | Show `detail` as a notice in the conversation, put the user's text back in the input |
| `404 not_found` | Session deleted or not this user's | Return to History |

When a message fails, nothing is saved. Putting the text back in the input lets the user try again.

**Important: replies are not connected yet.** Replies come from Emmanuel's safety and AI layer, which isn't plugged in
yet. Until it is, every message returns **`503 reply_unavailable`**. Sessions, history, opening and deleting all work
now. When Emmanuel connects his part, the same endpoint starts returning real replies, and you don't need any
frontend change for that.

Extra fields in the request body (for example `mode`) are ignored, so sending them does no harm.

## 6. Admin Dashboard: recent logs

`GET /api/admin/logs?limit=50` (admins only; `403` for other accounts) returns the newest events first:

```json
[
  { "time": "2026-10-21T20:35:00Z", "type": "Session", "event": "chat_request",
    "message": "Message received", "status": "OK", "environment": "development" }
]
```

This fits the dashboard's "Recent Logs" card. `type`, `message` and `status` (`OK`, `Warning`, `Error`) match the
sample data fields. `time` is an ISO date, so format it (for example `toLocaleTimeString`). Log entries never contain
what users wrote.

`GET /api/health` (no sign-in needed) returns
`{ "status": "healthy", "services": [{ "name": "Backend / API", "status": "Healthy" }, { "name": "Database", … }, { "name": "Logging", … }] }`.
You can use it for those rows of the "Architecture Health" card.

## 7. What the backend does NOT provide yet (keep the sample data)

These belong to other teammates and have **no endpoint yet**:

| Screen / feature | Owner | What to do for now |
|---|---|---|
| My Insights (`SAMPLE_ANALYTICS`) | Korey | Keep the sample data |
| Admin Dashboard numbers, safety decisions, AI cost card (`SAMPLE_ADMIN_ANALYTICS`) | Korey / Emmanuel | Keep the sample data; only Recent Logs (and optionally Architecture Health) can be real |
| Support & Crisis screen triggered by a message (old `concern` status) | Emmanuel | The backend never returns `concern` today; keep the screen reachable from the support bar |
| "Safety Check Unavailable" screen | Emmanuel | Will be triggered by `503 safety_unavailable` once his layer is connected |
| Journaling save and coping-tool counts | Not assigned to the backend yet | Keep the current frontend-only behaviour |

When Emmanuel adds `support` and `crisis` replies, the message response will gain fields such as `resources`. I'll
update this document and tell you before that change.

## 8. Places in the current `src/App.jsx` that change

These line numbers are from the current `src/App.jsx` in this folder:

| Line | Today | Replace with |
|---|---|---|
| 81 | Imports the mock `sendMessageToBackend` from `services/chatService.js` (keyword matching, no network) | A real service module calling the endpoints above |
| 307 | `conversationSessions` holds three hard-coded sample sessions | `GET /api/sessions` when the History screen opens |
| 843, 1114, 2525 | Conversation, Reflection Chat and Continue Session each call the mock | `POST /api/sessions/{id}/messages`, handling the errors in section 5 |
| ~420-445 | Login form submit: fake login, where the username "admin" means administrator (line 432) | Section 3 |
| 481 | "Prototype Placeholder login" note under the form | Can be removed or replaced with the "don't use your real name" hint |
| Sign Out buttons | Only clear local state | `POST /api/auth/logout`, then clear the token |
| 60-79, 242-256 | `localStorage` visit and conversation counters | Can be removed; the backend tracks session activity |

### Reference implementation

A fully connected frontend was drafted in the newer project folder (`AI-COMPANION-FOR-EMOTIONAL-WELLNESS-AND-SELF-REFLECTION-`):

- `src/services/apiClient.js`: base URL, token storage, timeouts, 401 handling
- `src/services/authService.js` and `src/services/chatService.js`
- `App.jsx`: the shared `deliverMessage()` function and the new `MessageBubble` component

These files were **not** copied here because the frontend is your area. They also expect endpoints that don't exist
in this backend yet: analytics, journal, coping usage, and `support` / `crisis` replies. Reuse what fits and review
it as your own work.

## 9. Checklist

- [ ] Add the `/api` proxy to `vite.config.js` (or set up `VITE_API_URL`)
- [ ] Real sign-in, account creation, restore on page load, sign-out, and a 401 return to the login screen
- [ ] Create sessions; list, open and delete History from the backend
- [ ] Send messages through the backend; show `detail` for errors; keep the text on failure
- [ ] Admin "Recent Logs" (and optionally "Architecture Health") from the backend
- [ ] Keep sample data on the screens listed in section 7
- [ ] Try the full flow against a local backend
