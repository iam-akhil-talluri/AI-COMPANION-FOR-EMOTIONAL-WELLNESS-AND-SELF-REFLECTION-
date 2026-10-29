/*
  MEMORY SERVICE

  Cross-session memory through the FastAPI backend. When a conversation goes quiet
  (or the user starts a new one) the backend writes a short, safety-checked note
  about it. The newest notes from the user's other conversations go with each reply,
  so the companion can pick up where they left off. Crisis conversations are never
  remembered.

  Memory is on by default. Users can turn it off (which deletes every note), and
  view or delete notes one at a time or all at once. Conversations stay in History.
*/

import { apiRequest } from './apiClient'
import { formatSessionDate } from './chatService'

function toUiMemory(memory) {
  return {
    enabled: memory.enabled,
    // False when memory is switched off on the server.
    available: memory.available,
    sessionsUsed: memory.sessions_used,
    notes: memory.notes.map((note) => ({
      sessionId: note.session_id,
      type: note.type,
      title: note.title || (note.type === 'reflection' ? 'Reflection' : 'Conversation'),
      summary: note.summary,
      date: formatSessionDate(note.last_active)
    }))
  }
}

export async function getMemory() {
  return toUiMemory(await apiRequest('/api/memory'))
}

export async function setMemoryEnabled(enabled) {
  return toUiMemory(await apiRequest('/api/memory/settings', { method: 'POST', body: { enabled } }))
}

export async function forgetNote(sessionId) {
  await apiRequest(`/api/memory/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}

export async function forgetAllNotes() {
  await apiRequest('/api/memory', { method: 'DELETE' })
}
