"""Tests for the admin analytics endpoint and the safety and AI health rows."""

import pytest

from app.config import get_settings
from tests.helpers import new_session, register, send


def analytics(client, headers, days=7):
    response = client.get(f"/api/admin/analytics?days={days}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def health_rows(client) -> dict:
    return {s["name"]: s for s in client.get("/api/health").json()["services"]}


def test_analytics_requires_admin(client, auth):
    assert client.get("/api/admin/analytics").status_code == 401
    assert client.get("/api/admin/analytics", headers=auth).status_code == 403


def test_empty_analytics(client, admin_auth):
    body = analytics(client, admin_auth)
    assert body["overview"] == {"active_users": 0, "total_sessions": 0, "sessions_per_user": 0}
    assert len(body["session_frequency"]) == 7 and len(body["ai_usage"]["daily"]) == 7
    assert body["ai_usage"]["requests"] == 0 and body["ai_usage"]["budget_utilization_pct"] is None


def test_analytics_counts_usage_safety_and_cost(client, admin_auth, openai):
    first, second = register(client, "user-one"), register(client, "user-two")
    session_one = new_session(client, first)
    send(client, first, session_one, "I had a long day")              # low, AI
    send(client, first, session_one, "Do I have depression?")         # moderate, AI with boundary note
    send(client, second, new_session(client, second), "I want to kill myself")  # high, template
    send(client, second, new_session(client, second), "I can't cope anymore")   # elevated, AI + support
    new_session(client, first)  # empty: not counted

    body = analytics(client, admin_auth)
    assert body["overview"] == {"active_users": 2, "total_sessions": 3, "sessions_per_user": 1.5}
    assert body["session_frequency"][-1]["count"] == 3

    safety = body["safety"]
    assert safety["messages_checked"] == 4 and safety["sent_to_ai_unchecked"] == 0
    assert safety["decisions"] == {"clear": 2, "concern": 2, "error": 0}
    assert safety["boundary_replies"] == 1
    assert {c["category"] for c in safety["by_category"]} == {"diagnosis_request", "suicidal_intent", "severe_distress"}
    assert body["escalations"] == {"total": 2, "crisis": 1, "support": 1}

    usage = body["ai_usage"]
    assert usage["requests"] == 3 and usage["replies_without_ai"] == 1
    assert (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]) == (2100, 120, 2220)
    assert usage["estimated_cost_usd"] == pytest.approx(3 * (700 * 0.15 + 40 * 0.60) / 1e6)
    assert usage["by_model"] == [{"model": "gpt-test", "requests": 3, "tokens": 2220,
                                  "cost_usd": usage["estimated_cost_usd"]}]
    assert usage["daily"][-1]["requests"] == 3 and usage["daily"][-1]["input_tokens"] == 2100


def test_safety_errors_are_counted(client, auth, admin_auth, openai, monkeypatch):
    monkeypatch.setattr(get_settings(), "use_openai_moderation", True)
    openai.moderations.create.side_effect = TimeoutError("down")
    send(client, auth, new_session(client, auth), "hello")
    safety = analytics(client, admin_auth)["safety"]
    assert safety["safety_check_errors"] == 1 and safety["decisions"]["error"] == 1
    assert health_rows(client)["Safety / Moderation"]["status"] == "Degraded"


def test_budget_utilization(client, auth, admin_auth, openai, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_monthly_budget_usd", 1.0)
    send(client, auth, new_session(client, auth), "hello")
    usage = analytics(client, admin_auth)["ai_usage"]
    assert usage["monthly_budget_usd"] == 1.0
    assert usage["budget_utilization_pct"] == pytest.approx(round(usage["month_to_date_cost_usd"] * 100, 1))


def test_health_rows_without_ai_key(client):
    rows = health_rows(client)
    assert rows["AI Service"]["status"] == "Not configured"
    assert rows["Safety / Moderation"] == {"name": "Safety / Moderation", "status": "Healthy", "detail": "rules only"}


def test_health_rows_with_ai(client, auth, openai):
    assert health_rows(client)["AI Service"]["status"] == "Healthy"
    openai.chat.completions.create.side_effect = ConnectionError("down")
    send(client, auth, new_session(client, auth), "hello")
    assert health_rows(client)["AI Service"]["status"] == "Degraded"
    openai.chat.completions.create.side_effect = None
    send(client, auth, new_session(client, auth), "hello again")
    assert health_rows(client)["AI Service"]["status"] == "Healthy"
