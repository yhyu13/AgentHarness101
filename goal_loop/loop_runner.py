from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from goal_loop.models import (
    AcceptanceCriterion,
    CheckerOutput,
    FinalResult,
    GoalSpec,
    LoopState,
    MakerOutput,
    RoundRecord,
    StopCondition,
    VerificationResult,
    Verdict,
)
from goal_loop.roles import Checker, Maker
from goal_loop.verifier import CommandVerifier
from goal_persistence import GoalRuntime, GoalStatus
from sandbox import Sandbox
from observability import TraceLog
from hippocampus import Hippocampus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GoalLoopRunner:
    """Orchestrate the goal loop on top of the durable ``goal_persistence`` runtime.

    Each round is: evaluate stop conditions -> maker -> checker -> machine verify ->
    record state -> apply usage -> decide. Completion requires machine evidence plus an
    independent PASS verdict; the maker's self-report alone never completes the goal.
    """

    def __init__(
        self,
        spec: GoalSpec,
        runtime: GoalRuntime,
        maker: Maker,
        checker: Checker,
        state_dir: str | Path | None = None,
        verifier: CommandVerifier | None = None,
        sandbox: Sandbox | None = None,
        trace_log: TraceLog | None = None,
        hippocampus: Hippocampus | None = None,
    ) -> None:
        self._spec = spec
        self._runtime = runtime
        self._maker = maker
        self._checker = checker
        self._verifier = verifier or CommandVerifier()
        self._sandbox = sandbox
        self._trace_log = trace_log
        self._hippocampus = hippocampus
        self._state_dir = Path(state_dir) if state_dir else Path(".")
        self._state = LoopState(loop_name=spec.objective)
        self._thread_id: Optional[str] = None

    # ------------------------------------------------------------------ helpers

    def _stop_condition(self, kind: str) -> Optional[StopCondition]:
        return next((sc for sc in self._spec.stop_conditions if sc.kind == kind), None)

    def _persist_state(self) -> None:
        if self._thread_id is None:
            return
        self._state_dir.mkdir(parents=True, exist_ok=True)
        path = self._state_dir / f"{self._thread_id}.loop_state.json"
        path.write_text(json.dumps(self._state.to_dict(), indent=2), encoding="utf-8")

    def _load_state(self) -> LoopState:
        path = self._state_dir / f"{self._thread_id}.loop_state.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return LoopState.from_dict(data)
        return LoopState(loop_name=self._spec.objective)

    def _verify_criterion(
        self, criterion: AcceptanceCriterion, checker: CheckerOutput
    ) -> tuple[bool, list[VerificationResult]]:
        """A criterion is satisfied by machine evidence, or by the checker when there
        is no command to run."""
        if criterion.verify_command:
            result = self._run_verification(criterion.verify_command)
            return result.ok, [result]
        satisfied = checker.verdict != Verdict.FAIL
        return satisfied, []

    def _run_verification(self, command: str) -> VerificationResult:
        """Run a verification command, optionally through the sandbox when provided.

        This is where the loop composes with the execution-environment layer: if a
        sandbox is wired in, commands are gated by its allowlist and fail-closed
        contract. Otherwise the plain ``CommandVerifier`` runs them.
        """
        if self._sandbox is None:
            return self._verifier.run(command)
        import shlex

        argv = shlex.split(command)
        result = self._sandbox.run(argv)
        return VerificationResult(
            command=command,
            returncode=result.returncode,
            timed_out=result.timed_out,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _build_evidence(
        self,
        criteria_satisfied: list[str],
        results: list[VerificationResult],
        checker: CheckerOutput,
    ) -> str:
        parts = [
            f"verdict={checker.verdict.value}",
            f"criteria={','.join(criteria_satisfied)}",
        ]
        for r in results:
            parts.append(f"{r.command}:{r.returncode}")
        return "; ".join(parts)

    # ------------------------------------------------------------------ loop

    def run(
        self,
        thread_id: str,
        budget_tokens: Optional[int] = None,
        budget_wall_ms: Optional[int] = None,
    ) -> GoalStatus:
        """Run the loop until completion, a stop condition, or a blocker threshold.

        ``budget_tokens`` / ``budget_wall_ms`` are forwarded to the underlying durable
        goal so budget auto-transition can fire through the loop.
        """
        self._thread_id = thread_id

        # Durable resume: reuse an existing active goal for this thread, otherwise
        # create one. This is what lets the loop survive a process restart.
        goal = self._runtime.get_goal(thread_id)
        if goal is None:
            goal = self._runtime.create_goal(
                thread_id,
                self._spec.objective,
                budget_tokens=budget_tokens,
                budget_wall_ms=budget_wall_ms,
            )
            self._state = LoopState(loop_name=self._spec.objective)
        elif not goal.is_active:
            return goal.status
        else:
            self._state = self._load_state()

        max_rounds = self._stop_condition("max_rounds")

        round_number = self._state.current_round
        rounds_this_run = 0
        prev_satisfied: set[str] = set()
        while True:
            # Budget / terminal check before doing work.
            if not goal.is_active:
                break
            if max_rounds and rounds_this_run >= max_rounds.value:
                self._finalize("stopped_max_rounds", "Maximum rounds reached")
                break

            round_number += 1
            rounds_this_run += 1
            record = RoundRecord(number=round_number, started_at=_now())

            # Idle self-start / anti-drift guard from the durable runtime.
            cont = self._runtime.maybe_continue(thread_id)
            if cont is None:
                self._finalize(
                    goal.status.value,
                    "Goal is not active (no continuation offered)",
                )
                break

            maker_output: MakerOutput = self._maker(
                self._spec, self._state, cont.steering_prompt
            )
            checker_output: CheckerOutput = self._checker(self._spec, maker_output)

            if self._trace_log is not None:
                self._trace_log.append(
                    "maker",
                    {"round": round_number, "summary": maker_output.summary},
                )
                self._trace_log.append(
                    "checker",
                    {"round": round_number, "verdict": checker_output.verdict.value},
                )
            if self._hippocampus is not None:
                traj_id = "".join(
                    c if c.isalnum() or c in "-_." else "_"
                    for c in f"{thread_id}-round-{round_number}"
                )
                traj = self._hippocampus.start_trajectory(traj_id)
                important = (
                    checker_output.issues[0].description
                    if checker_output.issues
                    else ""
                )
                self._hippocampus.record_step(
                    traj,
                    "make",
                    maker_output.summary,
                    important=important,
                )

            criteria_satisfied: list[str] = []
            results: list[VerificationResult] = []
            for criterion in self._spec.acceptance_criteria:
                ok, criterion_results = self._verify_criterion(criterion, checker_output)
                results.extend(criterion_results)
                if ok:
                    criteria_satisfied.append(criterion.id)

            record.maker_summary = maker_output.summary
            record.checker_verdict = checker_output.verdict
            record.issues = list(checker_output.issues)
            record.verification = results
            record.criteria_satisfied = criteria_satisfied
            record.finished_at = _now()

            self._state.files_changed += len(maker_output.modified_files)
            self._state.record_round(record)

            if self._trace_log is not None:
                self._trace_log.append(
                    "verification",
                    {"round": round_number, "criteria": criteria_satisfied},
                )

            # Account for the maker's and checker's real reported usage, so budget
            # auto-transition reflects actual work rather than a magic number.
            acc = self._runtime.start_turn(thread_id)
            acc.add_llm_call(
                input_tokens=maker_output.tokens_used + checker_output.tokens_used,
                cached_input_tokens=0,
                output_tokens=0,
            )
            goal = self._runtime.end_turn(thread_id)
            self._persist_state()

            # Budget terminal: stop immediately. Never mutate a terminal goal with a
            # blocked/complete transition, which would raise TransitionError.
            if not goal.is_active:
                self._finalize(
                    goal.status.value,
                    f"Goal reached terminal status {goal.status.value}",
                )
                break

            # Progress tracking for the blocked audit. We delegate the durable
            # three-strike transition to goal_persistence: mark_blocked increments the
            # blocked counter (flipping to BLOCKED after GoalRuntime.BLOCKED_THRESHOLD
            # consecutive observations), unblock resets it.
            # Monotonic progress: a round counts as progress only if it satisfies a
            # criterion it had not satisfied before. A checker that says PASS while the
            # machine commands keep failing therefore never counts as progress, so it
            # cannot evade the blocked audit and still fail to complete forever.
            satisfied_now = set(criteria_satisfied)
            round_made_progress = bool(satisfied_now - prev_satisfied)
            prev_satisfied = satisfied_now
            if round_made_progress:
                goal = self._runtime.unblock(thread_id)
            else:
                self._state.add_blocker(
                    checker_output.issues[0].description if checker_output.issues else "no progress"
                )
                goal = self._runtime.mark_blocked(thread_id, "no progress")
                if goal.status == GoalStatus.BLOCKED:
                    self._finalize("blocked", "No progress threshold reached")
                    break

            # Completion requires every criterion + independent pass verdict.
            all_satisfied = len(criteria_satisfied) == len(self._spec.acceptance_criteria)
            verdict_ok = checker_output.verdict in (Verdict.PASS, Verdict.ACCEPT_WITH_MINOR)
            if all_satisfied and verdict_ok:
                evidence = self._build_evidence(criteria_satisfied, results, checker_output)
                goal = self._runtime.mark_complete(thread_id, evidence)
                self._finalize(
                    "complete",
                    f"All acceptance criteria satisfied with evidence: {evidence}",
                )
                break

        return goal.status

    def _finalize(self, status: str, summary: str) -> None:
        self._state.status = status
        self._state.final_result = FinalResult(
            status=status,
            finished_at=_now(),
            summary=summary,
        )
        self._persist_state()
