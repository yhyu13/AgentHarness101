from __future__ import annotations

from typing import Protocol

from goal_loop.models import CheckerOutput, GoalSpec, LoopState, MakerOutput, Verdict


class Maker(Protocol):
    """A callable that implements work for a goal.

    The runner records the result but never trusts it for completion. It only feeds the
    maker the spec, durable loop state, and the anti-drift steering prompt. A real
    implementation would invoke an LLM and report the tokens it consumed.
    """

    def __call__(self, spec: GoalSpec, state: LoopState, steering: str) -> MakerOutput: ...


class Checker(Protocol):
    """A callable that independently verifies a maker's output.

    This is the only source of truth for a round verdict. In production it would be a
    different agent/session (or even a different model) than the maker, enforcing
    generator/evaluator separation.
    """

    def __call__(self, spec: GoalSpec, output: MakerOutput) -> CheckerOutput: ...


class EchoMaker:
    """Trivial in-memory maker used by tests and the demo."""

    def __init__(self, summary: str, modified_files: list[str] | None = None) -> None:
        self._summary = summary
        self._modified_files = modified_files or []

    def __call__(self, spec: GoalSpec, state: LoopState, steering: str) -> MakerOutput:
        return MakerOutput(
            summary=self._summary,
            modified_files=list(self._modified_files),
            self_verification="basic checks pass (maker self-report, untrusted)",
            risks="",
            tokens_used=len(steering) + len(self._summary),
        )


class StaticChecker:
    """A checker with a fixed verdict, used by tests and the demo."""

    def __init__(self, verdict: Verdict) -> None:
        self._verdict = verdict

    def __call__(self, spec: GoalSpec, output: MakerOutput) -> CheckerOutput:
        return CheckerOutput(
            verdict=self._verdict,
            tokens_used=len(output.summary),
        )
