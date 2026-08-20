# JOURNEY — Goal Persistence Harness

**Project:** AgentHarness101 / goal-persistence  
**Date range:** 2026-08-21  
**Legend:** `ME = the human`, `YOU = the AI (this build)`

---

## Era 1 — Skill activation

| ME | YOU |
|---|---|
| Pasted the `goal-persistence` skill spec and the `AgentHarness101` course outline. No explicit command, just the materials. | Loaded the `goal-persistence` skill. Read `00-课程大纲.md` to understand the course context (Harness 101, M5 state layer, Capstone). Inferred the task was to implement the spec as a course module. |

## Era 2 — Planning

| ME | YOU |
|---|---|
| (Implicit: proceed with implementation.) | Created a todo list with 6 steps: design data model, implement SQLite store, accounting, runtime, tests, README. Started with model + status machine design. |

## Era 3 — Core implementation

| ME | YOU |
|---|---|
| (No correction.) | Built `goal_persistence/models.py` (`Goal`, `GoalStatus`, `Usage`, transition rules), `store.py` (SQLite CRUD + schema), `accounting.py` (`TurnAccounting`), and `runtime.py` (`GoalRuntime` with idle self-start, resume, anti-drift prompt, blocked/completion audits). |

## Era 4 — First test run (FAILED)

| ME | YOU |
|---|---|
| (No correction.) | Wrote `tests/test_harness.py` and ran it. 16 passed, 4 failed: blocked-count logic did not accumulate across pre-blocked turns; `unblock` from `active` threw `TransitionError`; `mark_complete` dropped evidence; full-lifecycle test expected `blocked` after 3 observations but got `active`. |

## Era 5 — Bug fixes

| ME | YOU |
|---|---|
| (No correction.) | Fixed `models.py` to allow idempotent self-transitions and preserve completion evidence. Fixed `runtime.py` `mark_blocked` to accumulate `blocked_count` before status flips, and `unblock` to reset the counter even from `active`. Re-ran tests: 20 passed. |

## Era 6 — Documentation and demo

| ME | YOU |
|---|---|
| (Implicit: wrap up.) | Wrote `README.md`, `demo.py`, `pyproject.toml`. Ran demo successfully: steering prompt printed, turns tracked, resume on restart worked, completion with evidence worked. |

## Era 7 — The "no LLM" question

| ME | YOU |
|---|---|
| "No LLM dependency — the runtime drives the lifecycle and produces steering prompts, but the caller decides how to invoke the model. wait no LLM, how does this even work, can you show me run reuslt or test reuslts?" | Re-ran `pytest -v` (20 passed) and `demo.py`, then explained the separation of concerns: harness = memory + loop control + guardrails; LLM = inference engine. |

## Era 9 — Switch to MiniMax-M3 and capture LLM output

| ME | YOU |
|---|---|
| Provided `ANTHROPIC_MODEL=MiniMax-M3` and asked to dump test results to README, then wanted to know the actual LLM output. | Updated `llm_demo.py` to read `ANTHROPIC_MODEL` from env (defaulting to `MiniMax-M3`), added it to `.env`, and re-ran the demo. Result: 2 turns, `complete`, 948 / 5,000 tokens, no deprecation warning. Updated `README.md` with unit-test and LLM demo results. Explained that the demo truncates responses to 600 chars and does not persist full outputs. |

---

## How this project teaches vibe coding with AI

### The human's job

- **Decide the scope by dropping a spec.** The user provided the `goal-persistence` skill and course context; the AI inferred the build target. *(Era 1)*
- **Ask the clarifying "wait, how?" question.** The user's "no LLM, how does this work?" forced a clean separation-of-concerns explanation and a concrete demo. *(Era 7)*
- **Supply real credentials to validate integration.** The Anthropic token turned an abstract architecture claim into an observable LLM-driven loop. *(Era 8)*

### The AI's job

- **Build the smallest falsifiable unit first.** Implemented the status machine and store before any runtime sugar, so tests could catch transition bugs early. *(Era 3)*
- **Report failures honestly with evidence.** The first test run listed 4 specific failures; no hand-waving. *(Era 4)*
- **Fix with durable rules, not hacks.** The blocked-count fix became a general rule: accumulate observations before flipping state, reset on unblock. *(Era 5)*
- **Demonstrate, don't just describe.** When asked how the LLM fits, produced a runnable `llm_demo.py` and real API output. *(Era 8)*

### Portable rules

1. **A harness should not import the model; it should own state, budget, and loop control.** Proved by the fact that 20 tests pass with zero LLM calls, and the LLM demo only adds a thin caller layer. *(Eras 3–7)*
2. **State-machine transitions must be unit-tested, not eyeballed.** 4 of 20 tests specifically validate allowed/forbidden transitions and terminal-state behavior. *(Era 4)*
3. **Audit helpers need thresholds, not impulses.** `blocked` only flips after 3 consecutive observations; `complete` requires evidence. This prevents the model from declaring itself done. *(Era 5)*
4. **When the user says "how does this work?", run it and annotate the output.** The explanation landed because it was tied to actual `pytest` and `demo.py` output. *(Era 7)*
5. **Integration demos need real credentials and a bounded task.** A 2-turn Fibonacci task with a 5k token budget was enough to prove the loop without burning budget. *(Era 8)*

### One-sentence takeaway

**The human decides what to build and when to believe it; the AI builds falsifiable components, reports failures with evidence, and proves integration with the smallest real call possible.**
