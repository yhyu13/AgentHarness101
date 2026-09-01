"""Print every round of the whole-system E2E scenarios, side by side.

Runs the same two scenarios as ``tests/test_system_e2e.py`` — the happy path and the
adversarial fake-exit-0 path — and dumps each round's full conversation: what the
scripted maker said, how the checker voted, what the sandboxed ``@verify`` command
returned, what the world verifier read off disk, and how the loop ruled on progress /
completion.

Run:
    py -3 examples/system_e2e_trace.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from faux_provider import FauxMaker, FauxProvider
from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    GoalLoopRunner,
    GoalSpec,
    StaticChecker,
    StopCondition,
    Verdict,
)
from goal_loop.world_verifier import WorldCheck, WorldVerifier
from goal_persistence import GoalRuntime, GoalStore
from hippocampus import Hippocampus, HippocampusStore
from observability import TraceLog
from sandbox import Sandbox

EXPECTED = "hello world"


def _verify_command(artifact: Path, expected: str) -> str:
    code = (
        "import pathlib,sys;"
        "sys.exit(0 if pathlib.Path(sys.argv[1]).read_text()==sys.argv[2] else 1)"
    )
    path = str(artifact).replace("\\", "/")
    return f'py -c "{code}" "{path}" "{expected}"'


class _LyingChecker:
    def __call__(self, spec, output):
        return CheckerOutput(verdict=Verdict.PASS, tokens_used=0)


def _run(
    title: str,
    tmp: Path,
    *,
    maker,
    checker,
    world: WorldVerifier,
    verify_command: str,
    artifact: Path,
) -> None:
    print(f"\n{'=' * 72}")
    print(title)
    print(f"{'=' * 72}")

    sandbox = Sandbox(allowlist=["py"])
    trace = TraceLog(tmp / "trace.jsonl")
    hippocampus = Hippocampus(HippocampusStore(tmp / "memory"))
    provider = maker.provider

    spec = GoalSpec(
        objective="write a file containing hello world",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="c1",
                description="artifact equals hello world",
                verify_command=verify_command,
            )
        ],
        stop_conditions=[StopCondition(kind="max_rounds", value=10)],
    )

    runner = GoalLoopRunner(
        spec,
        GoalRuntime(GoalStore(tmp / "goals.db")),
        maker,
        checker,
        state_dir=tmp,
        sandbox=sandbox,
        trace_log=trace,
        hippocampus=hippocampus,
        world_verifier=world,
    )
    status = runner.run("thread-1")

    # Reconstruct per-round progress the same way the loop does: a round counts as
    # progress only when it newly satisfies a criterion it had not satisfied before.
    prev: set[str] = set()
    strikes = 0
    for i, r in enumerate(runner.state.rounds, start=1):
        now = set(r.criteria_satisfied)
        progress = bool(now - prev)
        prev = now
        if not progress:
            strikes += 1

        print(f"\n--- round {i} ---")
        print(f"  maker self-report : {r.maker_summary!r}")
        print(f"  checker verdict   : {r.checker_verdict.value if r.checker_verdict else 'n/a'}")
        for v in r.verification:
            extra = f"  stdout={v.stdout.strip()!r}" if v.stdout.strip() else ""
            print(f"  @verify           : {v.command} -> exit {v.returncode}{extra}")
        wv = world.verify(artifact, expected=EXPECTED)
        verdict = "OK" if wv.ok else "FAIL"
        print(
            f"  world verifier    : observed {wv.observed!r} vs expected {wv.expected!r} -> {verdict}"
        )
        if not wv.ok:
            print(f"      what: {wv.what}")
            print(f"      why : {wv.why}")
            print(f"      fix : {wv.fix}")
        print(f"  criteria satisfied: {','.join(r.criteria_satisfied) or '(none)'}")
        if progress:
            print("  loop ruling       : progress (new criterion) -> unblock")
        else:
            print(f"  loop ruling       : no progress -> blocked strike {strikes}")

    print(f"\n  final status      : {status.value}")
    print(f"  faux LLM calls    : {provider.call_count}")
    print(f"  trace events      : {[e.event_type for e in trace.replay()]}")


def main() -> None:
    root = Path(__file__).resolve().parent.parent / ".trace-demo"
    import shutil

    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)

    # --- happy path ---------------------------------------------------------
    happy_dir = root / "happy"
    happy_dir.mkdir(parents=True, exist_ok=True)
    happy_artifact = happy_dir / "out.txt"
    happy_artifact.write_text(EXPECTED, encoding="utf-8")

    _run(
        "Scenario 1 - happy path (correct artifact, real @verify, world OK)",
        happy_dir,
        maker=FauxMaker(FauxProvider(["wrote hello world"]), modified_files=[str(happy_artifact)]),
        checker=StaticChecker(Verdict.PASS),
        world=WorldVerifier([WorldCheck(happy_artifact, expected=EXPECTED)]),
        verify_command=_verify_command(happy_artifact, EXPECTED),
        artifact=happy_artifact,
    )

    # --- adversarial path ---------------------------------------------------
    adv_dir = root / "adversarial"
    adv_dir.mkdir(parents=True, exist_ok=True)
    adv_artifact = adv_dir / "out.txt"
    adv_artifact.write_text("wrong content", encoding="utf-8")

    _run(
        "Scenario 2 - adversarial (wrong artifact, fake exit-0, lying checker)",
        adv_dir,
        maker=FauxMaker(
            FauxProvider(["wrote hello world"] * 4), modified_files=[str(adv_artifact)]
        ),
        checker=_LyingChecker(),
        world=WorldVerifier([WorldCheck(adv_artifact, expected=EXPECTED)]),
        verify_command='py -c "pass"',
        artifact=adv_artifact,
    )

    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
