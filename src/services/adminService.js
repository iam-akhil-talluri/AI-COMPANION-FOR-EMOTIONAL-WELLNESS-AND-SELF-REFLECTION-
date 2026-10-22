/*
  ADMIN SERVICE

  The parts of the Admin Dashboard the backend provides today:
  - GET /api/admin/logs   recent operational events (admin role only; no message text)
  - GET /api/health       status of the backend, database and logging

  The other dashboard cards (usage, safety decisions, escalations, AI cost)
  have no backend endpoint yet and still use sample data in App.jsx.
*/

import { ApiError, apiRequest } from './apiClient'

export async function getRecentLogs(limit = 10) {
  return apiRequest(`/api/admin/logs?limit=${limit}`)
}

// /api/health answers 503 with the same body when the database is down or not
// migrated, so a 503 with a body is still a valid health report rather than an error.
export async function getHealth() {
  try {
    return await apiRequest('/api/health', { auth: false })
  } catch (error) {
    if (error instanceof ApiError && error.status === 503 && Array.isArray(error.data?.services)) {
      return error.data
    }
    throw error
  }
}

export function formatLogTime(isoDate) {
  return new Date(isoDate).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}
