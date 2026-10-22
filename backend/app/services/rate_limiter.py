"""In-memory sliding-window rate limiter.

State is per process. Use a shared store such as Redis when running multiple instances.
"""

import threading
import time
from collections import deque

# Periodically drop idle keys to bound memory use.
_SWEEP_EVERY = 1000
_SWEEP_IDLE_SECONDS = 3600


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        """Record a hit if within the limit; return False without recording otherwise."""
        return self.allow_all([(key, limit, window_seconds)])

    def allow_all(self, rules: list[tuple[str, int, float]]) -> bool:
        """Check several (key, limit, window) rules atomically.

        Hits are recorded only if every rule allows the request.
        """
        return self._check(rules, record=True)

    def peek_all(self, rules: list[tuple[str, int, float]]) -> bool:
        """Return True if every rule has room, without recording a hit."""
        return self._check(rules, record=False)

    def record(self, keys: list[str]) -> None:
        """Record a hit on each key without checking limits."""
        now = time.monotonic()
        with self._lock:
            for key in keys:
                self._hits.setdefault(key, deque()).append(now)

    def _check(self, rules: list[tuple[str, int, float]], record: bool) -> bool:
        now = time.monotonic()
        with self._lock:
            self._maybe_sweep(now)
            buckets = []
            for key, limit, window_seconds in rules:
                hits = self._hits.setdefault(key, deque())
                while hits and now - hits[0] >= window_seconds:
                    hits.popleft()
                if len(hits) >= limit:
                    return False
                buckets.append(hits)
            if record:
                for hits in buckets:
                    hits.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    def _maybe_sweep(self, now: float) -> None:
        self._calls += 1
        if self._calls % _SWEEP_EVERY:
            return
        idle = [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= _SWEEP_IDLE_SECONDS]
        for key in idle:
            del self._hits[key]


limiter = RateLimiter()


def check_chat_limits(key: str, per_minute: int, per_hour: int) -> bool:
    return limiter.allow_all([(f"chat:{key}:m", per_minute, 60), (f"chat:{key}:h", per_hour, 3600)])
