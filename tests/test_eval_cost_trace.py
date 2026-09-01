"""Cluster E tests: RegressionGate drift detection (E1), budget-guard refusal (E2),
cost trace events wired into observability (E3), and trace secret redaction (E4).

These pin the eval/cost/observability hardening independently of any LLM; every judge is
deterministic (ExactJudge) and every cost is derived from the layered pricing table.
"""

import json
from pathlib import Path

import pytest

from eval_harness import EvalReport, EvalResult, RegressionGate, Verdict
from cost_control import BudgetError, guard_budget, trace_cost
from observability import TraceLog


class TestRegressionGate:
    """E1: a live eval report is compared against a golden report to detect drift."""

    def test_no_regression_when_results_match(self) -> None:
        golden = EvalReport()
        golden.add(EvalResult("a", Verdict.PASS, "ok"))
        golden.add(EvalResult("b", Verdict.PASS, "ok"))
        gate = RegressionGate(golden=golden)
        live = EvalReport()
        live.add(EvalResult("a", Verdict.PASS, "ok"))
        live.add(EvalResult("b", Verdict.PASS, "ok"))
        assert gate.check(live).passed

    def test_detects_case_that_now_fails(self) -> None:
        golden = EvalReport()
        golden.add(EvalResult("a", Verdict.PASS, "ok"))
        gate = RegressionGate(golden=golden)
        live = EvalReport()
        live.add(EvalResult("a", Verdict.FAIL, "regressed"))
        result = gate.check(live)
        assert not result.passed
        assert "a" in result.regressions

    def test_detects_dropped_case(self) -> None:
        golden = EvalReport()
        golden.add(EvalResult("a", Verdict.PASS, "ok"))
        gate = RegressionGate(golden=golden)
        live = EvalReport()  # "a" no longer evaluated
        result = gate.check(live)
        assert not result.passed
        assert "a" in result.regressions

    def test_golden_saves_and_reloads(self, tmp_path: Path) -> None:
        golden = EvalReport()
        golden.add(EvalResult("a", Verdict.PASS, "ok"))
        golden.add(EvalResult("b", Verdict.FAIL, "known gap"))
        gate = RegressionGate(golden=golden)
        path = tmp_path / "golden.json"
        gate.save(path)
        reloaded = RegressionGate(golden_path=path)
        assert reloaded.golden.passed == 1
        assert reloaded.golden.total == 2


class TestBudgetGuard:
    """E2: refuse to start a run whose estimated cost exceeds the caller's ceiling."""

    def test_refuses_over_budget_start(self) -> None:
        with pytest.raises(BudgetError):
            guard_budget("mini", tokens_input=100_000, tokens_output=100_000, max_usd=1.0)

    def test_allows_within_budget_and_returns_cost(self) -> None:
        cost = guard_budget("mini", tokens_input=100, tokens_output=100, max_usd=1.0)
        assert cost > 0

    def test_unknown_model_still_fails_closed(self) -> None:
        with pytest.raises(KeyError):
            guard_budget("nope", tokens_input=1, tokens_output=1, max_usd=1.0)


class TestCostTraceEvent:
    """E3: each LLM call's cost is emitted as an inline trace event."""

    def test_emits_cost_event(self, tmp_path: Path) -> None:
        log = TraceLog(tmp_path / "session.jsonl")
        cost = trace_cost(log, "mini", tokens_input=1000, tokens_output=500)
        events = log.messages("cost")
        assert len(events) == 1
        assert events[0]["model"] == "mini"
        assert events[0]["tokens_input"] == 1000
        assert events[0]["cost_usd"] == pytest.approx(cost)


class TestTraceRedaction:
    """E4: secrets in a prompt payload are masked before they hit the append-only log."""

    def test_secret_key_never_persisted(self, tmp_path: Path) -> None:
        log = TraceLog(tmp_path / "session.jsonl")
        log.append("llm", {"prompt": "use api_key=sk-1234567890abcdef please"})
        serialized = json.dumps(log.replay()[0].payload)
        assert "sk-1234567890abcdef" not in serialized
        assert "REDACTED" in serialized

    def test_bearer_token_redacted(self, tmp_path: Path) -> None:
        log = TraceLog(tmp_path / "session.jsonl")
        log.append("llm", {"prompt": "Authorization: Bearer abcdefghij123456"})
        serialized = json.dumps(log.replay()[0].payload)
        assert "abcdefghij123456" not in serialized

    def test_redaction_can_be_opted_out(self, tmp_path: Path) -> None:
        log = TraceLog(tmp_path / "session.jsonl", redact_secrets=False)
        log.append("llm", {"prompt": "token=abc12345"})
        assert "abc12345" in log.replay()[0].payload["prompt"]
