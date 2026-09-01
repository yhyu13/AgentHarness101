"""Deterministic faux-provider tests for the goal loop.

These tests replace exactly one boundary — what the LLM says — and drive the real
goal loop (state machine, verifier, budget accounting, durable store) through a
scripted ``FauxMaker``. No real LLM API is ever invoked.
"""

from pathlib import Path

import pytest

from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    GoalLoopRunner,
    GoalSpec,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_persistence import GoalRuntime, GoalStatus, GoalStore
from faux_provider import FauxMaker, FauxProvider, FauxProviderExhausted


@pytest.fixture
def runtime(tmp_path: Path) -> GoalRuntime:
    return GoalRuntime(GoalStore(tmp_path / "goals.db"))


def make_spec(
    *,
    max_rounds: int | None = None,
    criteria: list[AcceptanceCriterion] | None = None,
) -> GoalSpec:
    stops: list[StopCondition] = []
    if max_rounds is not None:
        stops.append(StopCondition(kind="max_rounds", value=max_rounds))
    return GoalSpec(
        objective="Implement a goal loop",
        acceptance_criteria=criteria
        or [AcceptanceCriterion(id="c1", description="checker-decided")],
        stop_conditions=stops,
    )


class TestFauxProviderQueue:
    def test_fifo_consumption_order(self) -> None:
        provider = FauxProvider()
        provider.set_responses(["a", "b"])
        assert provider.generate("p1") == "a"
        assert provider.generate("p2") == "b"
        with pytest.raises(FauxProviderExhausted):
            provider.generate("p3")

    def test_call_count_increments_per_call(self) -> None:
        provider = FauxProvider()
        provider.append_responses(["x", "y", "z"])
        assert provider.call_count == 0
        provider.generate("p")
        provider.generate("p")
        provider.generate("p")
        assert provider.call_count == 3
        assert provider.get_pending_response_count() == 0

    def test_append_extends_existing_queue(self) -> None:
        provider = FauxProvider(["a"])
        provider.append_responses(["b", "c"])
        assert provider.get_pending_response_count() == 3
        assert provider.generate("p") == "a"
        assert provider.generate("p") == "b"
        assert provider.generate("p") == "c"


class TestFauxProviderEvents:
    def test_events_record_prompt_and_response(self) -> None:
        provider = FauxProvider(["first", "second"])
        provider.generate("prompt-1")
        provider.generate("prompt-2")
        calls = provider.events_of_type("call")
        assert len(calls) == 2
        assert calls[0]["prompt"] == "prompt-1"
        assert calls[0]["response"] == "first"
        assert calls[1]["prompt"] == "prompt-2"
        assert calls[1]["response"] == "second"
        assert len(provider.events) == 2

    def test_events_of_type_filters(self) -> None:
        provider = FauxProvider(["ok"])
        provider.generate("p")
        assert provider.events_of_type("call") == provider.events
        assert provider.events_of_type("nope") == []


class TestFauxProviderStream:
    def test_stream_yields_reply_and_records_call(self) -> None:
        provider = FauxProvider(["hello world"])
        chunks = list(provider.stream("p"))
        assert "".join(chunks) == "hello world"
        assert provider.call_count == 1
        assert provider.events_of_type("call")[0]["response"] == "hello world"

    def test_stream_with_rate_limit_yields_word_chunks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The ``tokens_per_second`` branch is real behavior, not dead code: it splits
        # the reply into whitespace-delimited chunks so a consumer can observe a
        # partial stream. Patch ``time.sleep`` to a no-op so the test has no wall-clock
        # dependence.
        monkeypatch.setattr("faux_provider.provider.time.sleep", lambda _s: None)
        provider = FauxProvider(["one two three"], tokens_per_second=1)
        chunks = list(provider.stream("p"))
        assert chunks == ["one ", "two ", "three"]
        assert "".join(chunks) == "one two three"
        assert provider.call_count == 1
        assert provider.events_of_type("call")[0]["response"] == "one two three"


class TestFauxResponseFactory:
    def test_factory_reads_context_and_state(self) -> None:
        seen: list = []

        def factory(context, state):
            seen.append((context, state))
            return f"echo:{context}"

        provider = FauxProvider([factory])
        out = provider.generate("ignored-prompt", context="STEERING", state={"round": 1})
        assert out == "echo:STEERING"
        assert seen == [("STEERING", {"round": 1})]

    def test_anti_drift_steering_reaches_factory(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # The critical evidence: the runner's anti-drift steering is actually handed
        # to the maker, and a dynamic factory can see it before choosing a reply.
        def echo_steering(context, state):
            return context

        provider = FauxProvider([echo_steering])
        maker = FauxMaker(provider)
        runner = GoalLoopRunner(
            make_spec(), runtime, maker, StaticChecker(Verdict.PASS), state_dir=tmp_path
        )
        status = runner.run("t1")
        assert status == GoalStatus.COMPLETE
        summary = runner._state.rounds[0].maker_summary
        assert "Keep the full objective intact" in summary
        assert "Implement a goal loop" in summary


class TestDeterminism:
    def test_scripted_output_is_byte_identical_across_ten_runs(self, tmp_path: Path) -> None:
        def run_once(i: int) -> str:
            runtime = GoalRuntime(GoalStore(tmp_path / f"db{i}.db"))
            provider = FauxProvider(["done"])
            maker = FauxMaker(provider)
            runner = GoalLoopRunner(
                make_spec(),
                runtime,
                maker,
                StaticChecker(Verdict.PASS),
                state_dir=tmp_path / f"state{i}",
            )
            status = runner.run("t1")
            responses = [e["response"] for e in provider.events_of_type("call")]
            return "|".join(responses) + "|" + status.value

        traces = [run_once(i) for i in range(10)]
        assert len(set(traces)) == 1


class TestComposition:
    def test_loop_completes_with_scripted_reply(self, runtime: GoalRuntime, tmp_path: Path) -> None:
        provider = FauxProvider(["implemented the feature"])
        maker = FauxMaker(provider)
        runner = GoalLoopRunner(
            make_spec(), runtime, maker, StaticChecker(Verdict.PASS), state_dir=tmp_path
        )
        status = runner.run("t1")
        assert status == GoalStatus.COMPLETE
        assert provider.call_count == 1
        assert runner._state.rounds[0].maker_summary == "implemented the feature"

    def test_maker_reports_tokens_from_reply_length(self) -> None:
        from goal_loop import LoopState

        provider = FauxProvider(["abcde"])
        maker = FauxMaker(provider)
        out = maker(make_spec(), LoopState(loop_name="x"), "steering")
        assert out.ok is True
        assert out.summary == "abcde"
        assert out.tokens_used == len("abcde")
        assert out.modified_files == []

    def test_maker_passes_modified_files(self) -> None:
        from goal_loop import LoopState

        provider = FauxProvider(["done"])
        maker = FauxMaker(provider, modified_files=["f1.py", "f2.py"])
        out = maker(make_spec(), LoopState(loop_name="x"), "steering")
        assert out.modified_files == ["f1.py", "f2.py"]

    def test_regression_2023_queued_slash_command_followup(
        self, runtime: GoalRuntime, tmp_path: Path
    ) -> None:
        # Historical bug: queued multi-round replies could be consumed out of order,
        # leaking a follow-up turn's reply into an earlier turn. Pin FIFO order
        # across loop rounds with a checker that fails first, then passes.
        scripted = ["attempt one", "attempt two"]
        provider = FauxProvider(scripted)

        class ScriptedChecker:
            def __init__(self, verdicts: list[Verdict]) -> None:
                self._verdicts = list(verdicts)
                self._i = 0

            def __call__(self, spec: GoalSpec, output) -> CheckerOutput:
                verdict = self._verdicts[self._i]
                self._i += 1
                return CheckerOutput(verdict=verdict, tokens_used=len(output.summary))

        maker = FauxMaker(provider)
        runner = GoalLoopRunner(
            make_spec(),
            runtime,
            maker,
            ScriptedChecker([Verdict.FAIL, Verdict.PASS]),
            state_dir=tmp_path,
        )
        status = runner.run("t1")

        assert status == GoalStatus.COMPLETE
        assert provider.call_count == 2
        responses = [e["response"] for e in provider.events_of_type("call")]
        assert responses == scripted
        assert runner._state.rounds[0].maker_summary == "attempt one"
        assert runner._state.rounds[1].maker_summary == "attempt two"
