from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """LLM-judge verdict for one eval case."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class EvalCase:
    """One input/output pair in the eval set."""

    id: str
    input: Any
    expected: Any


@dataclass(frozen=True, slots=True)
class EvalResult:
    """The judge's verdict for one case, with evidence."""

    case_id: str
    verdict: Verdict
    evidence: str


@dataclass(slots=True)
class EvalReport:
    """Aggregate result of running the eval set."""

    results: list[EvalResult] = field(default_factory=list)

    def add(self, result: EvalResult) -> None:
        self.results.append(result)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.PASS)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed_all(self) -> bool:
        return self.total > 0 and self.passed == self.total

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total": self.total,
            "results": [
                {
                    "case_id": r.case_id,
                    "verdict": r.verdict.value,
                    "evidence": r.evidence,
                }
                for r in self.results
            ],
        }
