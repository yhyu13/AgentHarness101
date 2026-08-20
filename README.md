# Goal Persistence Harness

A minimal, testable implementation of persistent agent goals: an objective that
keeps an agent working across turns, sessions, and process restarts until it is
genuinely complete.

Distilled from the Codex goal feature and aligned with the *Agent Harness 101*
curriculum.

## What it does

1. **Durable state** — one SQLite row per thread/context ID.
2. **Idle self-start** — when a thread is idle and the goal is active, produce a
   continuation steering prompt.
3. **Anti-drift steering** — every continuation re-injects the full objective
   and the completion/blocked audit contract.
4. **Resume** — on restart, re-read active goals and re-arm the idle loop.
5. **Budget auto-transition** — token or wall-time budget exceeded flips the
   goal to `budget_limited` inside the accounting write.

## Status machine

```text
Active → { Paused, Blocked, UsageLimited, BudgetLimited, Complete }
```

`Complete` and `BudgetLimited` are terminal. Invalid transitions are rejected.

## Project layout

```text
goal_persistence/
  __init__.py      # public API
  models.py        # Goal, GoalStatus, Usage, transition rules
  store.py         # SQLite schema + CRUD
  accounting.py    # TurnAccounting (in-memory per-turn deltas)
  runtime.py       # idle self-start, resume, audit helpers
tests/
  test_harness.py  # manual lifecycle tests against a real DB
```

## Install

```bash
uv venv
.venv\Scripts\activate  # Windows
uv pip install -e ".[dev]"
```

## Run tests

```bash
python -m pytest tests/test_harness.py -q
```

20 tests cover persistence, accounting, budget auto-transition, resume, blocked
audit, and a full manual lifecycle.

## Usage

```python
from goal_persistence import GoalRuntime, GoalStore, GoalStatus

runtime = GoalRuntime(GoalStore("goals.db"))

# Create a goal.
runtime.create_goal(
    thread_id="thread-1",
    objective="Implement a fail-closed sandbox for the agent harness",
    budget_tokens=10_000,
)

# When the thread goes idle, ask for a continuation.
cont = runtime.maybe_continue("thread-1")
if cont:
    print(cont.steering_prompt)

# Run a turn.
acc = runtime.start_turn("thread-1")
acc.add_llm_call(input_tokens=500, cached_input_tokens=50, output_tokens=150)
runtime.notify_tool_finish("thread-1")
goal = runtime.end_turn("thread-1")

# Complete only with evidence.
runtime.mark_complete("thread-1", "sandbox tests pass")
```

## Test results

### Unit tests

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_harness.py -q
```

```text
20 passed in 0.76s
```

| Test group | Count | Result |
|---|---|---|
| `TestStatusMachine` | 3 | passed |
| `TestPersistence` | 2 | passed |
| `TestAccounting` | 4 | passed |
| `TestIdleSelfStart` | 4 | passed |
| `TestResume` | 2 | passed |
| `TestBlockedAudit` | 2 | passed |
| `TestCompletionAudit` | 1 | passed |
| `TestLifecycleEvents` | 2 | passed |

### LLM demo

```bash
.\.venv\Scripts\python.exe llm_demo.py
```

Configuration (`.env`):

```ini
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ANTHROPIC_MODEL=MiniMax-M3
ANTHROPIC_AUTH_TOKEN=...
```

Result:

| Metric | Value |
|---|---|
| Goal | Write a small, well-documented Python function that computes the nth Fibonacci number iteratively, then briefly explain its time and space complexity |
| Model | `MiniMax-M3` |
| Turns executed | 2 |
| Final status | `complete` |
| Total tokens used | 948 / 5,000 budget |
| Evidence | LLM produced Fibonacci function |

The harness correctly re-injected the steering prompt each turn, tracked token usage, stayed under budget, and accepted completion with evidence.

**Captured LLM outputs** (demo truncates after 600 chars; full responses are not persisted):

Turn 1:

```text
I'll write a well-documented Python function that computes the nth Fibonacci number iteratively, then explain its complexity.

```python
def fibonacci(n):
    """
    Compute the nth Fibonacci number iteratively.

    The Fibonacci sequence is defined as:
        F(0) = 0, F(1) = 1
        F(n) = F(n-1) + F(n-2) for n >= 2

    Parameters
    ----------
    n : int
        The index (non-negative integer) of the desired Fibonacci number.

    Returns
    -------
    int
        The nth Fibonacci number.

    Raises
    ------
    ValueError
        If n is not a non-negative integer.

    Exam...
```

Turn 2:

```text
I'll write a well-documented Python function that computes the nth Fibonacci number iteratively, then explain its complexity.

```python
def fibonacci(n: int) -> int:
    """
    Compute the nth Fibonacci number iteratively.

    The Fibonacci sequence is defined as:
        F(0) = 0
        F(1) = 1
        F(n) = F(n-1) + F(n-2) for n >= 2

    Parameters
    ----------
    n : int
        The index (non-negative integer) of the desired Fibonacci number.

    Returns
    -------
    int
        The nth Fibonacci number.

    Raises
    ------
    ValueError
        If n is negative.
    Type...
```


