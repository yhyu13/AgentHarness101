"""Measure the harness's efficiency with real, non-fabricated signals.

Four independent dimensions, each returning a number that actually came from the
component rather than being injected and echoed back:

1. Loop: rounds and wall-clock time to verified completion (incremental maker).
2. Context compaction: characters in vs. characters kept + summary (reduction ratio).
3. Hippocampus memory: replay/retrospective wall-clock time and hit counts.
4. Sandbox: allowlisted executor vs. raw subprocess wall-clock overhead.

Run:
    py -3 examples/measure_efficiency.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    GoalLoopRunner,
    GoalSpec,
    MakerOutput,
    StopCondition,
    Verdict,
)
from goal_persistence import GoalRuntime, GoalStore
from context_compaction import ContextCompactor, ContextItem
from hippocampus import Hippocampus, HippocampusStore
from sandbox import Sandbox


def _measure_loop() -> dict:
    """Run a 2-criterion loop whose maker satisfies one criterion per round, and
    report the rounds and wall-clock time to verified completion."""
    db = Path(__file__).with_name("eff_loop.db")
    if db.exists():
        db.unlink()
    runtime = GoalRuntime(GoalStore(db))

    artifact_a = Path(__file__).with_name("eff_a.txt")
    artifact_b = Path(__file__).with_name("eff_b.txt")
    for p in (artifact_a, artifact_b):
        if p.exists():
            p.unlink()

    class IncrementalMaker:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, spec, state, steering: str) -> MakerOutput:
            self.calls += 1
            # Satisfy one criterion per round: work is genuinely incremental.
            if self.calls == 1:
                artifact_a.write_text("ok", encoding="utf-8")
            elif self.calls == 2:
                artifact_b.write_text("ok", encoding="utf-8")
            return MakerOutput(
                summary=f"incremental round {self.calls}",
                modified_files=[str(artifact_a), str(artifact_b)][: self.calls],
                tokens_used=0,  # not fabricating a token count; time is the signal
            )

    class ExactChecker:
        def __call__(self, spec, output: MakerOutput) -> CheckerOutput:
            ok = artifact_a.exists() and artifact_b.exists()
            return CheckerOutput(verdict=Verdict.PASS if ok else Verdict.FAIL)

    spec = GoalSpec(
        objective="produce two verified artifacts incrementally",
        acceptance_criteria=[
            AcceptanceCriterion(
                "a",
                "a == 'ok'",
                verify_command=f"py -c \"assert open({str(artifact_a)!r}).read() == 'ok'\"",
            ),
            AcceptanceCriterion(
                "b",
                "b == 'ok'",
                verify_command=f"py -c \"assert open({str(artifact_b)!r}).read() == 'ok'\"",
            ),
        ],
        stop_conditions=[StopCondition(kind="max_rounds", value=10)],
    )

    maker = IncrementalMaker()
    runner = GoalLoopRunner(spec, runtime, maker, ExactChecker())
    t0 = time.perf_counter()
    status = runner.run("eff-loop")
    elapsed = time.perf_counter() - t0

    return {
        "rounds": runner._state.current_round,
        "maker_calls": maker.calls,
        "status": status.value,
        "wall_seconds": round(elapsed, 4),
        "criteria_satisfied": (
            runner._state.rounds[-1].criteria_satisfied if runner._state.rounds else []
        ),
    }


def _measure_compaction() -> dict:
    items = [ContextItem(f"imp-{i}", f"CRITICAL fact {i}", important=True) for i in range(10)]
    items += [ContextItem(f"noise-{i}", f"verbose transcript line {i} " * 20) for i in range(90)]
    total_chars = sum(len(i.content) for i in items)

    compactor = ContextCompactor(threshold=0, threshold_ratio=0.8)
    archive = Path(__file__).with_name("eff_archive")
    result = compactor.compact_window(
        items, window_size=total_chars, archive_dir=archive, archive_name="a.json"
    )
    out_chars = sum(len(i.content) for i in result.kept) + len(result.summary)

    return {
        "items_in": len(items),
        "chars_in": total_chars,
        "kept_items": len(result.kept),
        "archived_items": len(result.archived),
        "chars_out": out_chars,
        "reduction_ratio": round(out_chars / total_chars, 4),
    }


def _measure_memory() -> dict:
    root = Path(__file__).with_name("eff_memory")
    memory = Hippocampus(HippocampusStore(root))
    traj = memory.start_trajectory("task-1")
    for i in range(5):
        memory.record_step(traj, f"step-{i}", "done", f"important fact {i}")
    memory.learn("config", "use-verify-first", correct=True)

    t0 = time.perf_counter()
    replay = memory.replay("task-1")
    retro = memory.retrospective()
    elapsed = time.perf_counter() - t0

    return {
        "trajectory_steps": len(replay.trajectory.steps),
        "important_lines": len(replay.important_lines),
        "correct_facts": len(retro),
        "replay_seconds": round(elapsed, 6),
    }


def _measure_sandbox() -> dict:
    sb = Sandbox(allowlist=["python"])
    n = 100

    t0 = time.perf_counter()
    for _ in range(n):
        sb.run(["python", "-c", "pass"])
    sandbox_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(n):
        subprocess.run(["python", "-c", "pass"], capture_output=True, shell=False)
    raw_s = time.perf_counter() - t0

    return {
        "commands": n,
        "sandbox_seconds": round(sandbox_s, 4),
        "raw_seconds": round(raw_s, 4),
        "overhead_ratio": round(sandbox_s / raw_s, 4) if raw_s else None,
    }


def main() -> None:
    report = {
        "loop": _measure_loop(),
        "compaction": _measure_compaction(),
        "memory": _measure_memory(),
        "sandbox": _measure_sandbox(),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    out = Path(__file__).with_name("efficiency_report.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()
