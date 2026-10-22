"""The companion reply provider: safety check, escalation, AI reply and output validation.

    message
     -> input safety check (rules + optional OpenAI Moderation)   fails closed: no AI if it breaks
     -> high risk:      reviewed crisis template + crisis resources (the AI is never called)
     -> abuse:          reviewed template + abuse resources (the AI is never called)
     -> elevated risk:  AI reply with a support note + support resources;
                        the reviewed template if the AI is unavailable or its reply is blocked
     -> moderate risk:  AI reply with a boundary note
     -> low risk:       AI reply
     -> output check on every AI reply; a failing reply is replaced with a reviewed template
     -> sanitize

Every reply the user sees is either reviewed template text or an AI reply that passed the
output check. This module stores nothing itself: chat_service persists the returned metrics.
"""

import logging
from collections.abc import Sequence

from app.config import Settings, get_settings
from app.content import resources_for, template
from app.services import ai_service
from app.services.ai_service import AIServiceError, estimate_cost
from app.services.reply_provider import (
    Reply,
    ReplyContext,
    ReplyUnavailableError,
    SafetyEventRecord,
    SafetyUnavailableError,
    Usage,
)
from app.services.safety_service import (
    RISK_ORDER,
    SafetyResult,
    SafetyServiceError,
    check_message,
    check_output,
    sanitize_output,
)

logger = logging.getLogger(__name__)

# Reviewed template for each category that can be escalated ("crisis" for anything else).
TEMPLATE_FOR = {
    "harmful_instructions": "harmful_instructions",
    "suicidal_intent": "crisis",
    "self_harm": "crisis",
    "immediate_danger": "immediate_danger",
    "harm_to_others": "harm_to_others",
    "abuse_disclosure": "abuse_disclosure",
    "severe_distress": "severe_distress",
    "isolation": "isolation",
    "negated_risk": "severe_distress",
    "concern_for_other": "concern_for_other",
}

# Elevated categories answered only with reviewed wording: the AI must not ask for details.
TEMPLATE_ONLY = {"abuse_disclosure"}

# Which resource set goes with an escalated category.
RESOURCE_KIND = {"abuse_disclosure": "abuse", "concern_for_other": "crisis"}


def screen(message: str, settings: Settings) -> SafetyResult:
    """Classify a message. Raises SafetyUnavailableError when the check can't complete."""
    try:
        return check_message(message, ai_service.moderation_client(settings))
    except (SafetyServiceError, AIServiceError) as exc:
        raise SafetyUnavailableError("safety_check_failed") from exc


def _resource_kind(safety: SafetyResult) -> str:
    if safety.risk_level == "high":
        return "abuse" if safety.primary_category == "abuse_disclosure" else "crisis"
    return RESOURCE_KIND.get(safety.primary_category or "", "support")


def _template_reply(safety: SafetyResult, events: list[SafetyEventRecord], action: str) -> Reply:
    status = "crisis" if safety.risk_level == "high" else "support"
    events.insert(0, SafetyEventRecord("input", safety.risk_level, safety.primary_category or "unknown", action,
                                       safety.source))
    return Reply(
        text=template(TEMPLATE_FOR.get(safety.primary_category or "", "crisis")),
        status=status, outcome=status, risk_level=safety.risk_level, categories=safety.categories,
        resources=resources_for(_resource_kind(safety)), safety_checked=True, safety_events=tuple(events),
    )


def _opening_prompt(context: Sequence[dict], info: ReplyContext) -> str | None:
    # Only while the whole session still fits in the context; later it would crowd out recent turns.
    return info.session_prompt if info.session_prompt and info.message_count <= len(context) else None


def companion_reply(context: Sequence[dict], message: str, info: ReplyContext,
                    settings: Settings | None = None) -> Reply:
    settings = settings or get_settings()
    safety = screen(message, settings)
    risk = safety.risk_level
    events: list[SafetyEventRecord] = []

    # High risk, and abuse disclosures: reviewed wording only. The AI is never called.
    if risk == "high":
        return _template_reply(safety, events, "crisis_template")
    if safety.escalated and safety.primary_category in TEMPLATE_ONLY:
        return _template_reply(safety, events, "support_template")

    if info.ai_budget_exhausted:
        if safety.escalated:
            return _template_reply(safety, events, "support_template")
        raise ReplyUnavailableError("budget_exceeded", risk)

    messages = ai_service.build_messages(
        context, message,
        session_type=info.session_type,
        opening_prompt=_opening_prompt(context, info),
        categories=safety.categories if RISK_ORDER[risk] >= RISK_ORDER["moderate"] else (),
        prior_risk=info.prior_risk,
    )
    try:
        result = ai_service.generate(messages, settings)
    except AIServiceError as exc:
        if safety.escalated:
            # Someone in distress always gets an answer and resources, even when the AI is down.
            logger.warning("AI unavailable for an escalated message (%s); using the reviewed template", exc.reason)
            return _template_reply(safety, events, "support_template")
        raise ReplyUnavailableError(exc.reason, risk) from exc

    usage = Usage(model=result.model, prompt_tokens=result.prompt_tokens,
                  completion_tokens=result.completion_tokens,
                  estimated_cost_usd=estimate_cost(result.prompt_tokens, result.completion_tokens, settings),
                  latency_ms=result.latency_ms)
    status = "support" if safety.escalated else "ok"
    resources = resources_for(_resource_kind(safety)) if safety.escalated else []
    if RISK_ORDER[risk] >= RISK_ORDER["moderate"]:
        action = "ai_with_support_note" if safety.escalated else "ai_with_boundary_note"
        events.append(SafetyEventRecord("input", risk, safety.primary_category or "unknown", action, safety.source))

    output = check_output(result.text, ai_service.moderation_client(settings))
    if output.safe:
        text, outcome = sanitize_output(result.text), status
    else:
        violation = output.violations[0]
        logger.warning("AI reply blocked by the output check: %s", violation)
        outcome = "blocked"
        if output.harmful:
            # Treat a harmful reply as a crisis: reviewed crisis wording and resources.
            events.append(SafetyEventRecord("output", "high", f"output_{violation}", "reply_blocked"))
            text, status, resources = template("crisis"), "crisis", resources_for("crisis")
        else:
            events.append(SafetyEventRecord("output", "moderate", f"output_{violation}", "reply_blocked"))
            text = (template(TEMPLATE_FOR.get(safety.primary_category or "", "severe_distress")) if safety.escalated
                    else template("output_blocked"))

    return Reply(
        text=text, status=status, outcome=outcome, risk_level=risk, categories=safety.categories,
        resources=resources, safety_checked=True, used_ai=True, usage=usage, safety_events=tuple(events),
    )
