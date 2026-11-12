/*
  FRONTEND SERVICE

  Sends chat messages to the FastAPI backend (POST /chat).

  The backend is responsible for safety screening,
  scope classification, and generating wellness responses.
  It returns { status, message, session_id } where status is
  'ok' | 'out_of_scope' | 'concern' | 'error'.
*/

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// sessionId: keeps the conversation's history together on the backend.
// history: messages already shown in this chat ({ role, text }), so the
// backend can pick up a restored session it has not seen before.
export async function sendMessageToBackend(userMessage, sessionId = null, history = []) {
  const response = await fetch(`${API_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: userMessage,
      session_id: sessionId === null ? null : String(sessionId),
      history
    })
  })

  if (!response.ok) {
    return {
      status: 'error',
      message: 'Sorry, I could not respond just now. Please try again.'
    }
  }

  return response.json()
}
