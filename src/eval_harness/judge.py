from __future__ import annotations

import threading
from typing import Callable, Optional, Protocol

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


class LLMJudge:
    """An LLM-backed judge that is fail-closed.

    It calls an LLM at the boundary (the ``llm`` callable returns a plain string) and
    maps the reply to a verdict. Any error, timeout, or unparseable reply is a ``FAIL``
    — an LLM-judge must never accidentally pass a case it could not actually evaluate.
    """

    def __init__(self, llm: Callable[[str], str], timeout_s: Optional[float] = None) -> None:
        self._llm = llm
        self._timeout_s = timeout_s

    def __call__(self, case: EvalCase, output: object) -> EvalResult:
        prompt = (
            "Judge whether this output satisfies the expected value. Reply with exactly "
            f"'pass' or 'fail'.\nexpected: {case.expected!r}\noutput: {output!r}"
        )
        try:
            reply = self._call_with_timeout(prompt)
        except Exception as exc:  # fail-closed: a dead judge never passes
            return EvalResult(
                case_id=case.id,
                verdict=Verdict.FAIL,
                evidence=f"judge error: {type(exc).__name__}: {exc}",
            )
        return EvalResult(case_id=case.id, verdict=self._parse(reply), evidence=reply)

    @staticmethod
    def _parse(reply: str) -> Verdict:
        lowered = reply.strip().lower()
        if lowered in ("pass", "passed", "yes", "true"):
            return Verdict.PASS
        return Verdict.FAIL  # anything unparseable is a fail, not a pass

    def _call_with_timeout(self, prompt: str) -> str:
        if self._timeout_s is None:
            return self._llm(prompt)
        box: dict = {}

        def run() -> None:
            try:
                box["value"] = self._llm(prompt)
            except Exception as exc:  # surfaced after the thread joins
                box["error"] = exc

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(self._timeout_s)
        if thread.is_alive():
            raise TimeoutError("judge timed out")
        if "error" in box:
            raise box["error"]
        return box.get("value", "")


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
