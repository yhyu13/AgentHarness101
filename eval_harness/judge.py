from __future__ import annotations

from typing import Callable, Protocol

from eval_harness.models import EvalCase, EvalReport, EvalResult, Verdict


class Judge(Protocol):
    """An independent evaluator: given a case and the produced output, return a verdict.

    The producer and judge must be separate (generator/evaluator split). In production
    this is an LLM-judge; here it is any callable, so the eval set runs without a model.
    """

    def __call__(self, case: EvalCase, output: object) -> EvalResult: ...


class ExactJudge:
    """Deterministic judge: output must equal the expected value."""

    def __call__(self, case: EvalCase, output: object) -> EvalResult:
        ok = output == case.expected
        return EvalResult(
            case_id=case.id,
            verdict=Verdict.PASS if ok else Verdict.FAIL,
            evidence=f"expected={case.expected!r}, got={output!r}",
        )


class EvalRunner:
    """Run an eval set against a subject function and an independent judge."""

    def __init__(self, subject: Callable[[object], object], judge: Judge) -> None:
        self._subject = subject
        self._judge = judge

    def run(self, cases: list[EvalCase]) -> EvalReport:
        report = EvalReport()
        for case in cases:
            output = self._subject(case.input)
            report.add(self._judge(case, output))
        return report
