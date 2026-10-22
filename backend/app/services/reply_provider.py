"""Pluggable reply generation.

The safety and AI layer (app/services/companion.py) is registered at startup with
`set_reply_provider()`. A provider receives the session's recent messages (oldest first),
the new message and a `ReplyContext`, and returns a `Reply`.

A simpler provider that takes only `(context, message)` and returns a string still works
(the demo-replies script and tests use one); its replies are recorded as not safety-checked.
Without a provider, sending a message fails with 503 and nothing is stored.
"""

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReplyContext:
    """What the backend knows about the session, beyond its recent messages."""

    session_id: str | None = None
    session_type: str = "conversation"
    # The opening prompt shown on screen, e.g. the chosen reflection prompt.
    session_prompt: str | None = None
    # Messages already in the session (the context may be only the most recent of them).
    message_count: int = 0
    # True when an earlier message in this session was escalated (elevated or high risk).
    prior_risk: bool = False
    # True when AI_MONTHLY_BUDGET_USD has been reached this month.
    ai_budget_exhausted: bool = False


@dataclass(frozen=True)
class SafetyEventRecord:
    stage: str  # input | output
    risk_level: str
    category: str
    action: str
    source: str = "rules"


@dataclass(frozen=True)
class Usage:
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass(frozen=True)
class Reply:
    text: str
    status: str = "ok"  # ok | support | crisis
    risk_level: str | None = None
    categories: tuple[str, ...] = ()
    resources: list[dict] = field(default_factory=list)
    safety_checked: bool = False
    used_ai: bool = False
    # Interaction outcome for metrics: ok | support | crisis | blocked
    outcome: str = "ok"
    usage: Usage = field(default_factory=Usage)
    safety_events: tuple[SafetyEventRecord, ...] = ()


class ReplyUnavailableError(RuntimeError):
    """No reply can be produced (AI unavailable, not configured, budget reached). `reason` is safe to log."""

    def __init__(self, reason: str = "unavailable", risk_level: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.risk_level = risk_level


class SafetyUnavailableError(ReplyUnavailableError):
    """The safety check could not run, so the message was not sent to the AI (fail closed)."""


ReplyProvider = Callable[..., Reply | str]

_provider: ReplyProvider | None = None
_takes_context: bool = False


def _accepts_reply_context(provider: ReplyProvider) -> bool:
    try:
        params = list(inspect.signature(provider).parameters.values())
    except (TypeError, ValueError):
        return False
    if any(p.kind is p.VAR_POSITIONAL for p in params):
        return True
    return len([p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]) >= 3


def set_reply_provider(provider: ReplyProvider | None) -> None:
    global _provider, _takes_context
    _provider = provider
    _takes_context = provider is not None and _accepts_reply_context(provider)


def is_configured() -> bool:
    return _provider is not None


def generate_reply(context: Sequence[dict], message: str, info: ReplyContext | None = None) -> Reply:
    if _provider is None:
        raise ReplyUnavailableError("no reply provider is registered")
    result = _provider(context, message, info or ReplyContext()) if _takes_context else _provider(context, message)
    return result if isinstance(result, Reply) else Reply(text=str(result))
