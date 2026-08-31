from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from goal_persistence.models import Usage


@dataclass
class TurnAccounting:
    """In-memory accumulator for a single turn.

    Tracks token deltas (input − cached_input + output) and wall-clock time.
    Flushes to the durable row on turn end.
    """

    tokens_input: int = 0
    tokens_cached_input: int = 0
    tokens_output: int = 0
    _start_ns: Optional[int] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._start_ns is None:
            self._start_ns = time.monotonic_ns()

    def add_llm_call(
        self, *, input_tokens: int, cached_input_tokens: int, output_tokens: int
    ) -> None:
        self.tokens_input += input_tokens
        self.tokens_cached_input += cached_input_tokens
        self.tokens_output += output_tokens

    def to_usage(self) -> Usage:
        elapsed_ms = 0
        if self._start_ns is not None:
            elapsed_ms = (time.monotonic_ns() - self._start_ns) // 1_000_000
        return Usage(
            tokens_input=self.tokens_input,
            tokens_cached_input=self.tokens_cached_input,
            tokens_output=self.tokens_output,
            wall_ms=elapsed_ms,
        )

    @property
    def tokens(self) -> int:
        return (self.tokens_input - self.tokens_cached_input) + self.tokens_output
