"""P1 hardening tests: LLM-judge fail-closed, per-model cost pricing, and trace spans.

All three extend existing layers without touching the LLM boundary: the LLM-judge calls a
plain string-returning callable, the pricing calculator is a pure function, and the trace
span only measures wall-clock duration around an already-appended event.
"""

import time
from pathlib import Path

import pytest

from eval_harness import EvalCase, LLMJudge, Verdict
from cost_control import TokenLedger, estimate_cost
from observability import TraceLog


def _case() -> EvalCase:
    return EvalCase("c1", input=2, expected=4)


class TestLLMJudge:
    def test_pass(self) -> None:
        judge = LLMJudge(lambda prompt: "pass")
        assert judge(_case(), 4).verdict == Verdict.PASS

    def test_fail(self) -> None:
        judge = LLMJudge(lambda prompt: "fail")
        assert judge(_case(), 5).verdict == Verdict.FAIL

    def test_fail_closed_on_llm_error(self) -> None:
        def boom(prompt: str) -> str:
            raise RuntimeError("provider down")

        result = LLMJudge(boom)(_case(), 4)
        assert result.verdict == Verdict.FAIL
        assert "provider down" in result.evidence

    def test_fail_closed_on_garbage_reply(self) -> None:
        judge = LLMJudge(lambda prompt: "maybe, sort of?")
        assert judge(_case(), 4).verdict == Verdict.FAIL

    def test_timeout_is_fail_closed(self) -> None:
        def slow(prompt: str) -> str:
            time.sleep(0.5)
            return "pass"

        judge = LLMJudge(slow, timeout_s=0.05)
        result = judge(_case(), 4)
        assert result.verdict == Verdict.FAIL
        assert "timed out" in result.evidence

    def test_timeout_path_surfaces_llm_error(self) -> None:
        def boom(prompt: str) -> str:
            raise RuntimeError("provider down")

        judge = LLMJudge(boom, timeout_s=1.0)
        result = judge(_case(), 4)
        assert result.verdict == Verdict.FAIL
        assert "provider down" in result.evidence

    def test_timeout_path_returns_value(self) -> None:
        judge = LLMJudge(lambda prompt: "pass", timeout_s=1.0)
        assert judge(_case(), 4).verdict == Verdict.PASS


class TestCostPricing:
    def test_estimate_cost_known_model(self) -> None:
        # mini: $0.10/1k in, $0.30/1k out.
        assert estimate_cost("mini", 1000, 0) == pytest.approx(0.10)
        assert estimate_cost("mini", 0, 1000) == pytest.approx(0.30)

    def test_estimate_cost_unknown_model_fails_closed(self) -> None:
        with pytest.raises(KeyError):
            estimate_cost("gpt-9000", 1000, 0)


class TestTraceSpan:
    def test_span_records_duration(self, tmp_path: Path) -> None:
        log = TraceLog(tmp_path / "session.jsonl")
        with log.span("work", unit="ms"):
            pass
        events = log.messages("work")
        assert len(events) == 1
        assert events[0]["unit"] == "ms"
        assert events[0]["duration_ms"] >= 0

    def test_span_appends_even_on_exception(self, tmp_path: Path) -> None:
        log = TraceLog(tmp_path / "session.jsonl")
        with pytest.raises(RuntimeError):
            with log.span("work"):
                raise RuntimeError("boom")
        events = log.messages("work")
        assert len(events) == 1
        assert "duration_ms" in events[0]


class TestTokenLedger:
    def test_totals_persist_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        first = TokenLedger(path)
        first.record(input_tokens=100, output_tokens=50)
        first.record(input_tokens=20, output_tokens=30)
        # A fresh instance reloads the same on-disk totals.
        second = TokenLedger(path)
        assert second.total_input() == 120
        assert second.total_output() == 80
        assert second.total_calls() == 2

    def test_report_format(self, tmp_path: Path) -> None:
        ledger = TokenLedger(tmp_path / "ledger.json")
        ledger.record(input_tokens=10, output_tokens=5)
        assert ledger.report() == "input=10 output=5 calls=1"

    def test_estimated_cost_delegates_to_pricing(self, tmp_path: Path) -> None:
        ledger = TokenLedger(tmp_path / "ledger.json")
        ledger.record(input_tokens=1000, output_tokens=0)
        assert ledger.estimated_cost("mini") == pytest.approx(0.10)

    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        ledger = TokenLedger(tmp_path / "nope.json")
        assert ledger.total_input() == 0
        assert ledger.total_output() == 0
        assert ledger.total_calls() == 0
