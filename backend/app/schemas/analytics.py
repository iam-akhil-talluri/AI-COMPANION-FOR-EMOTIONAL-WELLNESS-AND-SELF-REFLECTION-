from datetime import date

from pydantic import BaseModel


class Overview(BaseModel):
    active_users: int
    total_sessions: int
    sessions_per_user: float


class DayCount(BaseModel):
    date: date
    day: str
    count: int


class SafetyDecisions(BaseModel):
    clear: int
    concern: int
    error: int


class CategoryCount(BaseModel):
    category: str
    count: int


class SafetyStats(BaseModel):
    messages_checked: int
    safety_check_errors: int
    # Must always be 0: every AI call is preceded by a safety check.
    sent_to_ai_unchecked: int
    decisions: SafetyDecisions
    boundary_replies: int
    replies_blocked: int
    by_category: list[CategoryCount]


class Escalations(BaseModel):
    total: int
    crisis: int
    support: int


class ModelUsage(BaseModel):
    model: str
    requests: int
    tokens: int
    cost_usd: float


class DailyUsage(BaseModel):
    date: date
    day: str
    requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class AIUsage(BaseModel):
    model: str
    configured: bool
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    avg_cost_per_request_usd: float
    avg_latency_ms: int
    # Replies from reviewed templates (crisis and support): no AI cost.
    replies_without_ai: int
    month_to_date_cost_usd: float
    monthly_budget_usd: float | None
    budget_utilization_pct: float | None
    by_model: list[ModelUsage]
    daily: list[DailyUsage]


class AdminAnalytics(BaseModel):
    period_days: int
    overview: Overview
    session_frequency: list[DayCount]
    safety: SafetyStats
    escalations: Escalations
    ai_usage: AIUsage
