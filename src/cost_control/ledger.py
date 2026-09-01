from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cost_control.cost import estimate_cost


@dataclass
class TokenLedger:
    """A durable, cross-session accumulator of honest token usage.

    Persists running totals (input / output tokens, call count) to a JSON file so usage
    survives a process restart, and reports a one-line summary. It never invents a
    number: every value is fed by ``record``, which mirrors the honest accounting the
    loop already performs. ``estimated_cost`` folds in per-model pricing.
    """

    path: str | Path

    def __post_init__(self) -> None:
        self._path = Path(self.path)
        self._totals: dict[str, int] = self._load()

    def _load(self) -> dict[str, int]:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return {
                "input": int(data.get("input", 0)),
                "output": int(data.get("output", 0)),
                "calls": int(data.get("calls", 0)),
            }
        return {"input": 0, "output": 0, "calls": 0}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._totals), encoding="utf-8")

    def record(self, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self._totals["input"] += input_tokens
        self._totals["output"] += output_tokens
        self._totals["calls"] += 1
        self._save()

    def total_input(self) -> int:
        return self._totals["input"]

    def total_output(self) -> int:
        return self._totals["output"]

    def total_calls(self) -> int:
        return self._totals["calls"]

    def estimated_cost(self, model: str) -> float:
        return estimate_cost(model, self._totals["input"], self._totals["output"])

    def report(self) -> str:
        return (
            f"input={self._totals['input']} output={self._totals['output']} "
            f"calls={self._totals['calls']}"
        )
