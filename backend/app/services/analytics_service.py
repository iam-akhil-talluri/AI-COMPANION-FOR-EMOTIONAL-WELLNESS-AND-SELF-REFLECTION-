"""Admin analytics: usage, safety decisions, escalations and AI cost.

Built only from anonymized metadata (sessions, safety_events, interactions). No message text
and no usernames. Days are UTC calendar days.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import ConversationSession, Interaction, SafetyEvent
from app.db.types import utc_now
from app.services.chat_service import month_to_date_cost

CRISIS_ACTIONS = {"crisis_template"}
SUPPORT_ACTIONS = {"support_template", "ai_with_support_note"}


def _days(period_days: int) -> list[date]:
    today = utc_now().date()
    return [today - timedelta(days=offset) for offset in range(period_days - 1, -1, -1)]


def _day_label(day: date) -> str:
    return day.strftime("%a")


def admin_analytics(db: Session, period_days: int = 7, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    days = _days(period_days)
    since = utc_now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=period_days - 1)

    # --- Overview and session frequency (sessions with at least one message) --------
    used = (ConversationSession.message_count > 0,)
    active_users = db.scalar(select(func.count(func.distinct(ConversationSession.user_id)))
                             .where(ConversationSession.last_active >= since, *used)) or 0
    created = list(db.scalars(select(ConversationSession.created_at)
                              .where(ConversationSession.created_at >= since, *used)))
    per_day = Counter(moment.date() for moment in created)

    # --- Safety --------------------------------------------------------------------
    interactions = list(db.scalars(select(Interaction).where(Interaction.created_at >= since)))
    events = list(db.scalars(select(SafetyEvent).where(SafetyEvent.created_at >= since)))
    checked = [i for i in interactions if i.safety_checked]
    errors = sum(1 for i in interactions if i.status == "safety_error")
    crisis = sum(1 for e in events if e.action in CRISIS_ACTIONS or (e.stage == "output" and e.risk_level == "high"))
    support = sum(1 for e in events if e.action in SUPPORT_ACTIONS)
    by_category = Counter(e.category for e in events if e.stage == "input")

    # --- AI usage --------------------------------------------------------------------
    ai = [i for i in interactions if i.used_ai]
    input_tokens = sum(i.prompt_tokens for i in ai)
    output_tokens = sum(i.completion_tokens for i in ai)
    cost = sum(i.estimated_cost_usd for i in ai)
    daily: dict[date, dict] = defaultdict(lambda: {"requests": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0})
    models: dict[str, dict] = defaultdict(lambda: {"requests": 0, "tokens": 0, "cost": 0.0})
    for i in ai:
        day = daily[i.created_at.date()]
        day["requests"] += 1
        day["input_tokens"] += i.prompt_tokens
        day["output_tokens"] += i.completion_tokens
        day["cost"] += i.estimated_cost_usd
        model = models[i.model or "unknown"]
        model["requests"] += 1
        model["tokens"] += i.prompt_tokens + i.completion_tokens
        model["cost"] += i.estimated_cost_usd

    budget = settings.ai_monthly_budget_usd
    month_cost = month_to_date_cost(db)
    return {
        "period_days": period_days,
        "overview": {
            "active_users": active_users,
            "total_sessions": len(created),
            "sessions_per_user": round(len(created) / active_users, 1) if active_users else 0,
        },
        "session_frequency": [{"date": d, "day": _day_label(d), "count": per_day.get(d, 0)} for d in days],
        "safety": {
            "messages_checked": len(checked),
            "safety_check_errors": errors,
            "sent_to_ai_unchecked": sum(1 for i in ai if not i.safety_checked),
            "decisions": {
                "clear": sum(1 for i in checked if i.risk_level in ("low", "moderate")),
                "concern": sum(1 for i in checked if i.risk_level in ("elevated", "high")),
                "error": errors,
            },
            "boundary_replies": sum(1 for e in events if e.action == "ai_with_boundary_note"),
            "replies_blocked": sum(1 for e in events if e.stage == "output"),
            "by_category": [{"category": c, "count": n} for c, n in by_category.most_common()],
        },
        "escalations": {"total": crisis + support, "crisis": crisis, "support": support},
        "ai_usage": {
            "model": settings.openai_model,
            "configured": settings.ai_configured,
            "requests": len(ai),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated_cost_usd": round(cost, 6),
            "avg_cost_per_request_usd": round(cost / len(ai), 6) if ai else 0,
            "avg_latency_ms": round(sum(i.latency_ms for i in ai) / len(ai)) if ai else 0,
            "replies_without_ai": sum(1 for i in checked if not i.used_ai),
            "month_to_date_cost_usd": round(month_cost, 6),
            "monthly_budget_usd": budget,
            "budget_utilization_pct": round(month_cost / budget * 100, 1) if budget else None,
            "by_model": [{"model": m, "requests": v["requests"], "tokens": v["tokens"],
                          "cost_usd": round(v["cost"], 6)} for m, v in sorted(models.items())],
            # `daily` is a defaultdict, so days without AI requests come out as zeros.
            "daily": [{"date": d, "day": _day_label(d), "requests": daily[d]["requests"],
                       "input_tokens": daily[d]["input_tokens"], "output_tokens": daily[d]["output_tokens"],
                       "cost_usd": round(daily[d]["cost"], 6)} for d in days],
        },
    }
