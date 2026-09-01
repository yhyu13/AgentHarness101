from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True, slots=True)
class Price:
    """Per-model unit price, in USD per 1,000 tokens."""

    input_per_1k: float
    output_per_1k: float


# Illustrative tiered prices (USD / 1k tokens). Real vendor numbers are "待确认" and
# belong in a config/ledger keyed by the live model id; this table only pins the
# calculator's determinism, not real-world correctness.
PRICING: dict[str, Price] = {
    "mini": Price(input_per_1k=0.10, output_per_1k=0.30),
    "small": Price(input_per_1k=0.30, output_per_1k=0.90),
    "large": Price(input_per_1k=3.00, output_per_1k=15.00),
}


def estimate_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    """Estimate USD cost for ``model`` given honest input/output token counts.

    Unknown model raises ``KeyError`` (fail-closed: never silently price at 0).
    """
    if model not in PRICING:
        raise KeyError(f"no pricing for model {model!r}")
    price = PRICING[model]
    return (tokens_input * price.input_per_1k + tokens_output * price.output_per_1k) / 1000.0


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
