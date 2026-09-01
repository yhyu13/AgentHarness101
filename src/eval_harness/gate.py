from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from eval_harness.models import EvalReport, EvalResult, Verdict


@dataclass(frozen=True, slots=True)
class RegressionResult:
    """Whether a live eval report regressed relative to a golden report."""

    passed: bool
    golden_passed: int
    actual_passed: int
    total: int
    regressions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "golden_passed": self.golden_passed,
            "actual_passed": self.actual_passed,
            "total": self.total,
            "regressions": list(self.regressions),
        }


class RegressionGate:
    """Detect eval drift by diffing a live report against a stored golden report (E1).

    "No regression" means every case the golden says must pass still passes, and no case
    was dropped. A case that newly passes (golden=FAIL, live=PASS) is an improvement and
    does not trip the gate. The gate is the guardrail that makes "did this change make the
    subject better or worse?" answerable, instead of only reporting a fixed pass/fail set.
    """

    def __init__(
        self,
        golden: Optional[EvalReport] = None,
        golden_path: str | Path | None = None,
    ) -> None:
        if golden is None:
            if golden_path is None:
                raise ValueError("RegressionGate needs either a golden report or a path")
            golden = self._load(Path(golden_path))
        self._golden = golden

    @property
    def golden(self) -> EvalReport:
        return self._golden

    def check(self, report: EvalReport) -> RegressionResult:
        golden_by_id = {r.case_id: r.verdict for r in self._golden.results}
        live_by_id = {r.case_id: r.verdict for r in report.results}
        regressions = [
            cid
            for cid, verdict in golden_by_id.items()
            if verdict == Verdict.PASS and live_by_id.get(cid) != Verdict.PASS
        ]
        # A case that was once evaluated but is absent now is also a regression — the
        # eval set must not silently shrink.
        regressions.extend(cid for cid in golden_by_id if cid not in live_by_id)
        return RegressionResult(
            passed=not regressions,
            golden_passed=self._golden.passed,
            actual_passed=report.passed,
            total=report.total,
            regressions=list(dict.fromkeys(regressions)),
        )

    def save(self, path: str | Path) -> None:
        """Persist the golden report as JSON so a future run can be diffed against it."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self._golden.to_dict(), indent=2), encoding="utf-8")

    @staticmethod
    def _load(path: Path) -> EvalReport:
        data = json.loads(path.read_text(encoding="utf-8"))
        report = EvalReport()
        for r in data.get("results", []):
            report.add(
                EvalResult(
                    case_id=r["case_id"],
                    verdict=Verdict(r["verdict"]),
                    evidence=r.get("evidence", ""),
                )
            )
        return report
