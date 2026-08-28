# Agent Harness 101

A minimal, testable implementation of the agent harness across its six runtime layers
plus the safety and cost-control cross-cuts:

- **Context management** (`context_compaction/`)
- **Tool management** (`tool_registry/`)
- **Execution environment** (`sandbox/`)
- **State & memory** (`goal_persistence/`, `hippocampus/`)
- **Verification & eval** (`goal_loop/`, `eval_harness/`)
- **Observability & audit** (`observability/`)
- **Safety** (`safety/`) and **cost control** (`cost_control/`)

Distilled from the Codex goal feature and aligned with the *Agent Harness 101*
curriculum.

## Highlight features

- **Two-layer goal system** — `goal_persistence` makes a goal durable (SQLite row,
  idle self-start, anti-drift steering, resume, budget auto-transition); `goal_loop`
  makes it *run* (parse `goal.md`, maker/checker split, machine verification, stop
  conditions).
- **Generator/evaluator separation** — a maker's self-report never completes a goal;
  only an independent checker verdict plus machine-verified acceptance criteria can.
- **Composed runtime, not parallel toys** — `GoalLoopRunner` routes verification
  through a fail-closed `sandbox`, logs to an append-only `observability` trace, and
  records each round into `hippocampus` long-term memory.
- **Fail-closed execution** — an unconfigured sandbox refuses with
  `SANDBOX_UNAVAILABLE` instead of running bare; commands are allowlisted and run with
  `shell=False`.
- **Context compaction at 80%** — marked context stays verbatim, the rest is archived
  and summarized when the window crosses 80%.
- **Hippocampus long-term memory** — task trajectory → important-content index → local
  cache → learn/unlearn/correct → replay/retrospect.
- **Safety and cost cross-cuts** — RBAC + high-risk HITL + injection marker
  (`safety/`); token-bucket rate limiter + tool-result cache (`cost_control/`).
- **Measured, not asserted** — `examples/measure_efficiency.py` reports real numbers
  (rounds, compaction ratio, replay latency, sandbox overhead) in
  `doc/02_goal_loop/efficiency.md`.

## Modules

| Module | What it owns | Source |
|---|---|---|
| `goal_persistence/` | Durable state, idle self-start, anti-drift steering, resume, budget auto-transition | Codex goal feature |
| `goal_loop/` | `goal.md` parsing, maker/checker split, machine verification, loop state, stop conditions | `learn-harness-engineering` Lecture 13 / Project 07 |
| `context_compaction/` | 80% cutoff, keep marked verbatim, archive + summarize the rest | Study guide layer ① |
| `hippocampus/` | Task trajectory, important-content index, local cache, learn/unlearn, replay | Study guide layer ④ |
| `tool_registry/` | Register tools, permission labels, least privilege, schema validation | Study guide layer ② |
| `sandbox/` | Fail-closed allowlist executor (not an OS-level jail) | Study guide layer ③ |
| `eval_harness/` | Eval set + deterministic ExactJudge (swap in an LLM-judge) | Study guide layer ⑤ |
| `observability/` | Append-only trace log + byte-level replay | Study guide layer ⑥ |
| `safety/` | RBAC roles, high-risk HITL, prompt-injection marker | Study guide M6 |
| `cost_control/` | Token-bucket rate limiter + tool-result cache | Study guide M5.7 |

`goal_loop` also ships `registered_roles.py`, which routes the maker/checker through a
`ToolRegistry` permission gate — so the last "parallel toys" gap (loop → tool registry)
is closed by construction, not by prose.

The `goal_loop` composes the persistence layer rather than reimplementing it:
`GoalLoopRunner` drives `GoalRuntime` for durable goals, and delegates the
blocked/complete audits to it. The other layers are independent and compose the same
way — each is a small, tested unit with a runnable demo.

## What goal_persistence does

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
goal_persistence/            # durable goal state machine (state layer)
  __init__.py                # public API
  models.py                  # Goal, GoalStatus, Usage, transition rules
  store.py                   # SQLite schema + CRUD
  accounting.py              # TurnAccounting (in-memory per-turn deltas)
  runtime.py                 # idle self-start, resume, audit helpers
goal_loop/                   # maker/checker verification loop (verification layer)
  loop_runner.py             # loop driver
  models.py                  # GoalSpec, AcceptanceCriterion, LoopState
  roles.py                   # Maker / Checker protocols (generator/evaluator split)
  verifier.py                # CommandVerifier (argv-based, shell=False)
  templates/                 # goal.md, loop-state.md, maker/checker prompts
context_compaction/          # context management layer (80% cutoff compaction)
  compactor.py               # keep marked, archive + summarize the rest
  summarizer.py              # pluggable ExtractiveSummarizer (swap in an LLM)
hippocampus/                 # long-term memory layer
  memory.py                  # Hippocampus: record, index, learn/unlearn, replay
  store.py                   # on-disk trajectories + memory index + cache
tool_registry/               # tool management layer
  registry.py                # ToolRegistry: permission gate + schema validation
sandbox/                     # execution environment layer
  sandbox.py                 # fail-closed allowlist executor (shell=False + timeout)
eval_harness/                # verification & eval layer
  judge.py                   # EvalRunner + ExactJudge (deterministic, not an LLM)
observability/               # observability & audit layer
  trace.py                   # append-only TraceLog + replay
safety/                      # safety cross-cut
  safety.py                  # SafetyGuard: RBAC + HITL + injection marker
cost_control/                # cost cross-cut
  cost.py                    # RateLimiter + ToolResultCache
examples/                    # runnable demos (run from repo root)
  demo.py                    # goal persistence demo
  goal_loop_demo.py          # fail-then-pass loop demo
  llm_demo.py                # real LLM demo (needs ANTHROPIC_AUTH_TOKEN)
  llm_goal_loop.py           # real LLM maker + machine checker (needs MINIMAX_API_KEY)
  context_compaction_demo.py # 80% cutoff demo
  hippocampus_demo.py        # trajectory + learn/unlearn + replay demo
  harness_layers_demo.py     # registry/sandbox/eval/trace/safety/cost demo
tests/
  test_harness.py            # goal_persistence lifecycle tests
  test_goal_loop.py          # goal_loop verification tests
  test_context_compaction.py # context compaction tests
  test_hippocampus.py        # long-term memory tests
  test_harness_layers.py     # registry/sandbox/eval/trace/safety/cost tests
doc/
  course/                    # TASK.md + 00-课程大纲.md (curriculum)
  harness-1hour.html         # one-hour interactive study guide
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

79 tests total: persistence 20, `goal_loop` 27, `context_compaction` 9, `hippocampus`
6, `harness_layers` 16, and `efficiency` 2.

## Goal loop usage

```python
from pathlib import Path

from goal_loop import GoalLoopRunner, GoalSpec
from goal_persistence import GoalRuntime, GoalStore

spec = GoalSpec.from_markdown("goal.md")  # human-authored contract
runtime = GoalRuntime(GoalStore("goals.db"))

runner = GoalLoopRunner(
    spec,
    runtime,
    maker,      # a callable (spec, state, steering) -> MakerOutput
    checker,    # an independent callable (spec, output) -> CheckerOutput
)

status = runner.run("thread-1")
assert status.value == "complete"
```

The loop only completes when every acceptance criterion is machine-verified and the
independent checker returns a non-FAIL verdict. A maker's self-report never completes
the goal.

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
.\.venv\Scripts\python.exe examples\llm_demo.py
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


