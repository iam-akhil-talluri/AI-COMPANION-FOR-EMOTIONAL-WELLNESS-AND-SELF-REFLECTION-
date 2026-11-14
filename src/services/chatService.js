/*
  FRONTEND SERVICE

  Sends chat messages to the FastAPI backend (POST /chat).

  The backend is responsible for safety screening,
  scope classification, and generating wellness responses
  grounded in approved resources (RAG).

  Response: { status, message, session_id, sources }
    status: 'ok' | 'out_of_scope' | 'concern' | 'error'
    sources: approved resources the reply drew on
             [{ documentId, title, sourceUrl }]

  Set VITE_API_URL in a frontend .env file if the backend is not
  running on http://localhost:8000.
*/

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ERROR_RESPONSE = {
  status: 'error',
  message: 'Sorry, I could not respond just now. Please try again.',
  sources: []
}

// sessionId: keeps one conversation's history together on the backend.
// history: messages already shown in this chat ({ role, text }), so the
// backend can pick up a restored session it has not seen before.
export async function sendMessageToBackend(userMessage, sessionId = null, history = []) {
  try {
    const response = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: userMessage,
        session_id: sessionId === null || sessionId === undefined ? null : String(sessionId),
        history: history
          .filter((m) => m && (m.role === 'user' || m.role === 'assistant'))
          .map((m) => ({ role: m.role, text: m.text || '' }))
          .slice(-100)
      })
    })

    if (!response.ok) {
      return ERROR_RESPONSE
    }

    return await response.json()
  } catch {
    // Backend not running or network unavailable.
    return ERROR_RESPONSE
  }
}
