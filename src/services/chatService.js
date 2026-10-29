/*
  CHAT SERVICE

  Sessions, conversation history and sending messages, through the FastAPI backend.

  Flow for every message:
  React → POST /api/sessions/{id}/messages → safety check → (AI reply with an
  output check, or a reviewed support message) → backend saves both → React

  The backend fails closed: if the safety check cannot run it answers
  503 safety_unavailable and the message never reaches the AI.
*/

import { ApiError, apiRequest } from './apiClient'

// Backend limit (MAX_MESSAGE_CHARS).
export const MAX_MESSAGE_LENGTH = 2000

// API messages use `content`; the screens use `text`.
function toUiMessage(message) {
  return {
    id: message.id,
    role: message.role,
    text: message.content,
    createdAt: message.created_at
  }
}

export function formatSessionDate(isoDate) {
  return new Date(isoDate).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric'
  })
}

function toUiSession(session) {
  return {
    id: session.id,
    type: session.type,
    date: formatSessionDate(session.last_active),
    createdAt: session.created_at,
    lastActive: session.last_active,
    title: session.title || (session.type === 'reflection' ? 'Reflection' : 'Conversation'),
    prompt: session.prompt,
    messageCount: session.message_count,
    // Safety-checked memory note, shown as the History preview (null until written).
    summary: session.summary || null
  }
}

export async function createSession({ type = 'conversation', prompt = null, title = null } = {}) {
  const session = await apiRequest('/api/sessions', {
    method: 'POST',
    body: { type, prompt, title }
  })
  return toUiSession(session)
}

// History page: newest activity first. type: 'conversation' | 'reflection' | null; q: search text.
// Resolves to { sessions, total } where total counts every match, not just this page.
export async function listSessions({ type = null, q = '', limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (type) params.set('type', type)
  if (q.trim()) params.set('q', q.trim())

  const { data, headers } = await apiRequest(`/api/sessions?${params}`, { withHeaders: true })
  const sessions = data.map(toUiSession)
  const total = Number(headers.get('X-Total-Count'))
  return { sessions, total: Number.isFinite(total) && total >= offset ? total : offset + sessions.length }
}

// Every session with its messages, as the JSON the backend sends (for "Download my history").
export async function exportHistory() {
  return apiRequest('/api/sessions/export')
}

// Deletes every session, its messages and memory note.
export async function deleteAllSessions() {
  await apiRequest('/api/sessions', { method: 'DELETE' })
}

export async function getSession(sessionId) {
  const session = await apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}`)
  return {
    ...toUiSession(session),
    messages: session.messages.map(toUiMessage)
  }
}

export async function deleteSession(sessionId) {
  await apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}

/*
  Sends one message and returns:
    { status: 'ok',      message }             show the reply
    { status: 'support', message, resources }  show the reply with support resources under it
    { status: 'crisis',  message, resources }  show the reply, then the Support & Crisis Resources screen
    { status: 'error',   message }             the safety check could not run (fail closed)
  Other failures (AI unavailable, rate limit, length limit, expired sign-in,
  network) throw an ApiError whose message is safe to show in the conversation.
*/
export async function sendMessageToBackend(sessionId, userMessage) {
  try {
    const data = await apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: 'POST',
      body: { content: userMessage }
    })

    return {
      status: data.status,
      message: data.response,
      resources: data.resources || []
    }
  } catch (error) {
    if (error instanceof ApiError && error.code === 'safety_unavailable') {
      return { status: 'error', message: error.message }
    }
    throw error
  }
}
