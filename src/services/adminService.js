/*
  ADMIN SERVICE

  Admin Dashboard data from the backend (admin role only; no message text or usernames):
  - GET /api/admin/analytics  usage, safety decisions, escalations, AI tokens and cost
  - GET /api/admin/logs       recent operational events
  - GET /api/health           status of the backend, database, logging, safety layer and AI

  Coping Tool Activity has no backend endpoint yet and keeps sample data in App.jsx.
*/

import { ApiError, apiRequest } from './apiClient'

// Maps GET /api/admin/analytics to the shape the dashboard cards use.
export async function getAdminAnalytics(days = 7) {
  const data = await apiRequest(`/api/admin/analytics?days=${days}`)
  const { overview, safety, escalations, ai_usage: ai } = data

  return {
    activeUsers: overview.active_users,
    totalSessions: overview.total_sessions,
    sessionsPerUser: overview.sessions_per_user,
    messagesSafetyChecked: safety.messages_checked,
    safetyCheckErrors: safety.safety_check_errors,
    sentToAIUnchecked: safety.sent_to_ai_unchecked,
    weekdays: data.session_frequency.map((item) => ({ day: item.day, count: item.count })),
    escalations: escalations.total,
    crisisEscalations: escalations.crisis,
    supportEscalations: escalations.support,
    safetyDecisions: safety.decisions,
    boundaryReplies: safety.boundary_replies,
    repliesBlocked: safety.replies_blocked,
    aiUsage: {
      model: ai.model,
      configured: ai.configured,
      requests: ai.requests,
      inputTokens: ai.input_tokens,
      outputTokens: ai.output_tokens,
      totalTokens: ai.total_tokens,
      estimatedCost: ai.estimated_cost_usd,
      avgCostPerRequest: ai.avg_cost_per_request_usd,
      avgLatencyMs: ai.avg_latency_ms,
      repliesWithoutAI: ai.replies_without_ai,
      monthToDateCost: ai.month_to_date_cost_usd,
      monthlyBudget: ai.monthly_budget_usd,
      budgetUtilization: ai.budget_utilization_pct,
      byModel: ai.by_model,
      daily: ai.daily.map((item) => ({
        day: item.day,
        requests: item.requests,
        inputTokens: item.input_tokens,
        outputTokens: item.output_tokens,
        cost: item.cost_usd
      }))
    }
  }
}

// Small amounts need more decimals: $0.000128 should not show as $0.00.
export function formatUsd(amount) {
  if (!amount) return '$0.00'
  return amount >= 0.01 ? `$${amount.toFixed(2)}` : `$${amount.toFixed(6)}`
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString('en-US')
}

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
