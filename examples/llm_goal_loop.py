"""Run the goal loop with a real MiniMax LLM as the maker, and report actual token usage.

This closes the "run a real LLM and report actual tokens" TODO. The maker is an LLM
call that implements a small, verifiable artifact; the checker is a machine command.

Run:
    $env:MINIMAX_API_KEY = "..."  # or export MINIMAX_API_KEY=...
    py -3 examples/llm_goal_loop.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import anthropic

from goal_loop import (
    AcceptanceCriterion,
    CheckerOutput,
    CommandVerifier,
    GoalLoopRunner,
    GoalSpec,
    MakerOutput,
    Scope,
    StopCondition,
    Verdict,
)
from goal_persistence import GoalRuntime, GoalStatus, GoalStore


MODEL = os.environ.get("ANTHROPIC_MODEL", "MiniMax-M3")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
# MODEL/BASE_URL/AUTH_TOKEN come from the ANTHROPIC_* env triplet; keep the key
# aligned to the same triplet (the llm-proxy endpoint) instead of preferring the
# legacy MiniMax key.
API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("MINIMAX_API_KEY")


class LlmMaker:
    """An LLM maker that writes a Python artifact with a required function."""

    def __init__(self, client: anthropic.Anthropic, artifact: Path) -> None:
        self._client = client
        self._artifact = artifact

    def __call__(self, spec: GoalSpec, state, steering: str) -> MakerOutput:
        prompt = (
            f"{steering}\n\n"
            "Write a Python file whose content is exactly:\n"
            "def answer():\n"
            "    return 42\n"
            "No explanation, only the code."
        )
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=steering,
            messages=[{"role": "user", "content": prompt}],
        )
        # Thinking models return a ThinkingBlock before the TextBlock; pull the
        # text block only (skip .thinking) so `code` holds the actual answer.
        code = "".join(b.text for b in response.content if b.type == "text")
        # Keep only the def block; ignore any extra prose.
        start = code.find("def answer")
        if start != -1:
            self._artifact.write_text(code[start:].strip(), encoding="utf-8")
        # Total usage = input + output. Do NOT subtract cache_read_input_tokens:
        # the proxy reports them as separate, non-overlapping buckets, so
        # subtracting drives the total negative on cache hits.
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return MakerOutput(
            summary=f"LLM wrote artifact ({len(code)} chars)",
            modified_files=[str(self._artifact)] if self._artifact.exists() else [],
            tokens_used=tokens,
        )


class MachineChecker:
    """Independent machine checker: imports the artifact and asserts answer()==42."""

    def __init__(self, artifact: Path) -> None:
        self._artifact = artifact

    def __call__(self, spec: GoalSpec, output: MakerOutput) -> CheckerOutput:
        result = CommandVerifier().run(
            f"py -c \"import importlib.util; s=importlib.util.spec_from_file_location('a', {str(self._artifact)!r}); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert m.answer() == 42\""
        )
        verdict = Verdict.PASS if result.ok else Verdict.FAIL
        return CheckerOutput(verdict=verdict, command_results=[result], tokens_used=0)


def main() -> None:
    if not API_KEY:
        print("Set MINIMAX_API_KEY (or ANTHROPIC_AUTH_TOKEN) to run this demo.")
        return

    client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY)
    artifact = Path(__file__).with_name("llm_goal_loop_artifact.py")
    if artifact.exists():
        artifact.unlink()
    db = Path(__file__).with_name("llm_goal_loop.db")
    if db.exists():
        db.unlink()

    spec = GoalSpec(
        objective="Produce a Python function answer() returning 42",
        acceptance_criteria=[
            AcceptanceCriterion(
                "answer-42",
                "imported module has answer() == 42",
                verify_command=(
                    f"py -c \"import importlib.util; s=importlib.util.spec_from_file_location('a', {str(artifact)!r}); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert m.answer() == 42\""
                ),
            )
        ],
        scope=Scope(fair_game=[str(artifact)], hands_off=["goal_persistence/"]),
        stop_conditions=[StopCondition(kind="max_rounds", value=5)],
    )

    runtime = GoalRuntime(GoalStore(db))
    maker = LlmMaker(client, artifact)
    checker = MachineChecker(artifact)
    runner = GoalLoopRunner(spec, runtime, maker, checker)

    status = runner.run("llm-goal-loop")
    goal = runtime.get_goal("llm-goal-loop")

    print("=" * 60)
    print(f"Model: {MODEL}")
    print(f"Final status: {status.value}")
    print(f"Rounds: {runner._state.current_round}")
    print(f"Actual tokens used: {goal.usage.tokens}")
    print(f"  (input={goal.usage.tokens_input}, output={goal.usage.tokens_output})")
    print(f"Evidence: {goal.last_blocked_reason}")
    print("=" * 60)

    assert status == GoalStatus.COMPLETE
    assert goal.usage.tokens > 0
    print("Done.")


if __name__ == "__main__":
    main()
