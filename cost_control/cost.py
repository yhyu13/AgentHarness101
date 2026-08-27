from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True, slots=True)
class RateLimit:
    """A token-bucket rate limiter: max ``capacity`` calls per ``period_s`` seconds."""

    capacity: int
    period_s: float


@dataclass
class RateLimiter:
    """Token-bucket limiter for provider calls (QPS/RPM/TPM)."""

    limit: RateLimit

    def __post_init__(self) -> None:
        self._tokens = float(self.limit.capacity)
        self._last = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(
            float(self.limit.capacity),
            self._tokens + elapsed * (self.limit.capacity / self.limit.period_s),
        )
        self._last = now
        if self._tokens < 1.0:
            return False
        self._tokens -= 1.0
        return True


@dataclass
class ToolResultCache:
    """Cache tool results keyed by input, with a TTL.

    Only deterministic tools should be cached; this is an explicit opt-in, matching the
    "tool result cache" cost-control idea from the study guide.
    """

    ttl_s: float = 60.0

    def __post_init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        at, value = entry
        if time.monotonic() - at > self.ttl_s:
            del self._store[key]
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)
