"""Demo: goal persistence harness driving a real Anthropic-compatible LLM.

Uses environment variables:
    ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
    ANTHROPIC_AUTH_TOKEN=...
    ANTHROPIC_MODEL=MiniMax-M3
"""

import os
from pathlib import Path

import anthropic

from goal_persistence import GoalRuntime, GoalStatus, GoalStore

DB = Path(__file__).with_name("llm_demo_goals.db")
if DB.exists():
    DB.unlink()

MODEL = os.environ.get("ANTHROPIC_MODEL", "MiniMax-M3")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
API_KEY = os.environ["ANTHROPIC_AUTH_TOKEN"]

client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY)
runtime = GoalRuntime(GoalStore(DB))

OBJECTIVE = (
    "Write a small, well-documented Python function that computes the nth Fibonacci "
    "number iteratively, then briefly explain its time and space complexity."
)

runtime.create_goal(
    thread_id="llm-demo-thread",
    objective=OBJECTIVE,
    budget_tokens=5_000,
)

print("=" * 60)
print(f"Goal: {OBJECTIVE}")
print(f"Model: {MODEL}")
print(f"Base URL: {BASE_URL}")
print("=" * 60)

max_turns = 2
for turn in range(1, max_turns + 1):
    cont = runtime.maybe_continue("llm-demo-thread")
    if cont is None:
        print(f"\n[Turn {turn}] No continuation offered (goal not active).")
        break

    print(f"\n--- Turn {turn} ---")
    print("[Harness] Steering prompt re-injected.")

    response = client.messages.create(
        model=MODEL,
        max_tokens=1_024,
        system=cont.steering_prompt,
        messages=[
            {"role": "user", "content": "Continue working on the objective."},
        ],
    )

    assistant_text = response.content[0].text
    print(f"[LLM] {assistant_text[:600]}{'...' if len(assistant_text) > 600 else ''}")

    acc = runtime.start_turn("llm-demo-thread")
    acc.add_llm_call(
        input_tokens=response.usage.input_tokens,
        cached_input_tokens=response.usage.cache_read_input_tokens or 0,
        output_tokens=response.usage.output_tokens,
    )
    goal = runtime.end_turn("llm-demo-thread")

    print(
        f"[Harness] Turn ended: status={goal.status.value}, "
        f"tokens_used={goal.usage.tokens}, budget={goal.budget_tokens}"
    )

    if goal.status == GoalStatus.BUDGET_LIMITED:
        print("[Harness] Budget exhausted. Stopping.")
        break

# Mark complete with the final assistant output as evidence.
final_goal = runtime.mark_complete("llm-demo-thread", "LLM produced Fibonacci function")
print("\n" + "=" * 60)
print(f"Final status: {final_goal.status.value}")
print(f"Evidence: {final_goal.last_blocked_reason}")
print(f"Total tokens: {final_goal.usage.tokens}")
print("=" * 60)
