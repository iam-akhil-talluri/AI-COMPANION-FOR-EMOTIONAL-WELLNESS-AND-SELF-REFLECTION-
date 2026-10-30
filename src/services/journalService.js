/*
  JOURNAL SERVICE

  Private journal entries (Coping Tools > Journaling) through the FastAPI backend.
  Only the author can read their entries; no AI reads or answers them.
  Every entry is safety-checked when saved:
    { status: 'ok' }                     saved
    { status: 'support', resources }     saved; show the support resources
    { status: 'crisis',  resources }     saved; open the Support & Crisis Resources screen
  Entries older than the server's retention period are deleted automatically.
*/

import { apiRequest } from './apiClient'

// Backend limit (MAX_JOURNAL_CHARS).
export const MAX_JOURNAL_LENGTH = 5000

function toUiEntry(entry) {
  return {
    id: entry.id,
    prompt: entry.prompt,
    text: entry.content,
    createdAt: entry.created_at,
    date: new Date(entry.created_at).toLocaleString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    })
  }
}

// Newest first. Resolves to { entries, total, retentionDays }.
export async function listJournal({ limit = 10, offset = 0 } = {}) {
  const data = await apiRequest(`/api/journal?limit=${limit}&offset=${offset}`)
  return {
    entries: data.entries.map(toUiEntry),
    total: data.total,
    retentionDays: data.retention_days
  }
}

export async function saveJournalEntry(text, prompt = null) {
  const data = await apiRequest('/api/journal', {
    method: 'POST',
    body: { content: text, prompt }
  })
  return {
    entry: toUiEntry(data.entry),
    status: data.status,
    resources: data.resources || []
  }
}

export async function deleteJournalEntry(entryId) {
  await apiRequest(`/api/journal/${encodeURIComponent(entryId)}`, { method: 'DELETE' })
}
