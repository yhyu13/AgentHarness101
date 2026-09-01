"""Demo of the goal persistence harness.

Run from the repo root:
    python examples/demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from goal_persistence import GoalRuntime, GoalStore

DB = Path(__file__).with_name("demo_goals.db")
if DB.exists():
    DB.unlink()

runtime = GoalRuntime(GoalStore(DB))

# 1. Create an active goal with a token budget.
runtime.create_goal(
    thread_id="demo-thread",
    objective="Implement a fail-closed sandbox for the agent harness",
    budget_tokens=10_000,
)

# 2. Idle self-start: the runtime offers a continuation steering prompt.
cont = runtime.maybe_continue("demo-thread")
assert cont is not None
print("=== Steering prompt ===")
print(cont.steering_prompt)
print()

# 3. Simulate a turn: LLM call + tool finish.
acc = runtime.start_turn("demo-thread")
acc.add_llm_call(input_tokens=500, cached_input_tokens=50, output_tokens=150)
runtime.notify_tool_finish("demo-thread")
goal = runtime.end_turn("demo-thread")
print(f"After turn 1: status={goal.status.value}, tokens={goal.usage.tokens}")

# 4. Simulate another turn with a tool error.
acc2 = runtime.start_turn("demo-thread")
runtime.notify_tool_error("demo-thread", "rate limited")
acc2.add_llm_call(input_tokens=200, cached_input_tokens=0, output_tokens=80)
goal = runtime.end_turn("demo-thread")
print(f"After turn 2: status={goal.status.value}, tokens={goal.usage.tokens}")

# 5. Resume on restart: a new runtime sees the same active goal.
new_runtime = GoalRuntime(GoalStore(DB))
continuations = new_runtime.resume_all()
print(f"Resumed {len(continuations)} active goal(s)")

# 6. Mark complete with evidence.
final = new_runtime.mark_complete("demo-thread", "sandbox tests pass")
print(f"Final: status={final.status.value}, evidence={final.last_blocked_reason}")

# 7. No continuation after completion.
assert new_runtime.maybe_continue("demo-thread") is None
print("Done.")
