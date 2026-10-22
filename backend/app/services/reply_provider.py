"""Pluggable reply generation.

The safety and AI layer registers a provider with `set_reply_provider()`. A provider
receives the session's recent messages (oldest first) and the new message, and returns
the reply text. Without a provider, sending a message fails with 503 and nothing is stored.
"""

from collections.abc import Callable, Sequence

ReplyProvider = Callable[[Sequence[dict], str], str]

_provider: ReplyProvider | None = None


class ReplyUnavailableError(RuntimeError):
    """Raised when no reply can be produced."""


def set_reply_provider(provider: ReplyProvider | None) -> None:
    global _provider
    _provider = provider


def is_configured() -> bool:
    return _provider is not None


def generate_reply(context: Sequence[dict], message: str) -> str:
    if _provider is None:
        raise ReplyUnavailableError("no reply provider is registered")
    return _provider(context, message)
