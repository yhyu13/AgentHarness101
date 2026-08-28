# JOURNEY — Agent Harness 101

**Project:** AgentHarness101
**Date range:** 2026-08-21 → 2026-08-28
**Legend:** `ME = the human`, `YOU = the AI (this build)`

This single journey merges the two earlier per-module histories
(`doc/01_goal_persistence/journey.md` and `doc/02_goal_loop/journey.md`) into one
chronological spine: the durable goal core first, then the loop and the six-layer
harness on top.

---

## Part 1 — Goal persistence (the durable core)

### Era 1 — Skill activation

| ME | YOU |
|---|---|
| Pasted the `goal-persistence` skill spec and the `AgentHarness101` course outline. No explicit command, just the materials. | Loaded the `goal-persistence` skill. Read `00-课程大纲.md` to understand the course context (Harness 101, M5 state layer, Capstone). Inferred the task was to implement the spec as a course module. |

### Era 2 — Planning

| ME | YOU |
|---|---|
| (Implicit: proceed with implementation.) | Created a todo list with 6 steps: design data model, implement SQLite store, accounting, runtime, tests, README. Started with model + status machine design. |

### Era 3 — Core implementation

| ME | YOU |
|---|---|
| (No correction.) | Built `goal_persistence/models.py` (`Goal`, `GoalStatus`, `Usage`, transition rules), `store.py` (SQLite CRUD + schema), `accounting.py` (`TurnAccounting`), and `runtime.py` (`GoalRuntime` with idle self-start, resume, anti-drift prompt, blocked/completion audits). |

### Era 4 — First test run (FAILED)

| ME | YOU |
|---|---|
| (No correction.) | Wrote `tests/test_harness.py` and ran it. 16 passed, 4 failed: blocked-count logic did not accumulate across pre-blocked turns; `unblock` from `active` threw `TransitionError`; `mark_complete` dropped evidence; full-lifecycle test expected `blocked` after 3 observations but got `active`. |

### Era 5 — Bug fixes

| ME | YOU |
|---|---|
| (No correction.) | Fixed `models.py` to allow idempotent self-transitions and preserve completion evidence. Fixed `runtime.py` `mark_blocked` to accumulate `blocked_count` before status flips, and `unblock` to reset the counter even from `active`. Re-ran tests: 20 passed. |

### Era 6 — Documentation and demo

| ME | YOU |
|---|---|
| (Implicit: wrap up.) | Wrote `README.md`, `demo.py`, `pyproject.toml`. Ran demo successfully: steering prompt printed, turns tracked, resume on restart worked, completion with evidence worked. |

### Era 7 — The "no LLM" question

| ME | YOU |
|---|---|
| "No LLM dependency — the runtime drives the lifecycle and produces steering prompts, but the caller decides how to invoke the model. wait no LLM, how does this even work, can you show me run reuslt or test reuslts?" | Re-ran `pytest -v` (20 passed) and `demo.py`, then explained the separation of concerns: harness = memory + loop control + guardrails; LLM = inference engine. |

### Era 8 — Switch to MiniMax-M3 and capture LLM output

| ME | YOU |
|---|---|
| Provided `ANTHROPIC_MODEL=MiniMax-M3` and asked to dump test results to README, then wanted to know the actual LLM output. | Updated `llm_demo.py` to read `ANTHROPIC_MODEL` from env (defaulting to `MiniMax-M3`), added it to `.env`, and re-ran the demo. Result: 2 turns, `complete`, 948 / 5,000 tokens, no deprecation warning. Explained that the demo truncates responses to 600 chars and does not persist full outputs. |

---

## Part 2 — Goal loop (the contract layer)

### Era 9 — Task arrival and repo triangulation

| ME | YOU |
|---|---|
| `/goal` with a five-step directive: migrate the goal harness, write a plan and self-criticize it, implement and self-criticize, self-test and loop on bugs, then dump a journey. Source: `D:\GitRepo-AI\learn-harness-engineering`. | Read both repos. Found the source's "goal harness" is not a runnable file — it is Lecture 13's `/goal` loop (goal + verification + stop condition) plus Project 07's maker/checker split, concretized in four templates. Found this repo already has `goal_persistence/`. |

### Era 10 — Locating the real gap

| ME | YOU |
|---|---|
| (No correction.) | Established the two repos describe different layers: the source's goal harness is the **loop contract**, this repo's `goal_persistence` is the **durable core**. The migration should add the loop layer on top, not re-implement SQLite/idle-resume/budget. |

### Era 11 — Plan draft + self-critique

| ME | YOU |
|---|---|
| (Implicit: proceed.) | Wrote `doc/02_goal_loop/plan.md`, then self-criticized the first draft: cut a redundant `VerificationMethod` abstraction, made completion machine-grounded, defined exact completion evidence, renamed ambiguous roles, removed a filesystem-touching demo. |

### Era 12 — Implementation + self-critique

| ME | YOU |
|---|---|
| (No correction.) | Built `goal_loop/` composing `goal_persistence.GoalRuntime`, then self-criticized and fixed four bugs: budget-then-blocked `TransitionError`, broken durable resume, a fake three-strike reimplementation, and non-round-trippable state serialization. |

### Era 13 — Self-test (FAILED, then fixed)

| ME | YOU |
|---|---|
| (No correction.) | Tests exposed round-number reset on resume and cumulative `max_rounds`. Fixed both; corrected a flawed test. Suite: 33 passing. |

### Era 14 — First review rejects "done"

| ME | YOU |
|---|---|
| Delivered a structured 工作审视报告: happy-path loop is real, but "goal harness migrated" is not — no `goal.md` parsing, steering dropped, fake usage, Windows-only verifier, PASS bypassed blocked, private `_store`, no course wiring, demo stamped pre-existing success. | Accepted the review and re-opened the work. |

### Era 15 — Contract-migration completion

| ME | YOU |
|---|---|
| (Review serves as the correction.) | Implemented every must-fix: `GoalSpec.from_markdown`, steering into maker, real usage, argv-based verifier, monotonic progress, public `get_goal`, course wiring, fail-then-pass demo. |

---

## Part 3 — The six-layer harness

### Era 16 — Context management (①)

| ME | YOU |
|---|---|
| Pointed at `doc/harness-1hour.html` layer ① and described the 80% cutoff idea. | Built `context_compaction/`: keep marked verbatim, archive + summarize the rest. |

### Era 17 — Hippocampus long-term memory (④)

| ME | YOU |
|---|---|
| Pointed at layer ④ and described the hippocampus idea. | Built `hippocampus/`: trajectory + index + cache + learn/unlearn + replay. |

### Era 18 — Remaining layers + cross-cuts

| ME | YOU |
|---|---|
| (Goal continues; the gap table is the spec.) | Filled the rest: `tool_registry/`, `sandbox/`, `eval_harness/`, `observability/`, `safety/`, `cost_control/`. |

### Era 19 — Second review: layers were parallel, not composed

| ME | YOU |
|---|---|
| Delivered a second review: demo's `verify_command` was a bare comparison that always exited 0; the "six layers" never called each other; `unlearn` left cache; 80% ratio was a dead constant; `system:` over-broad; SQLite sidecars not ignored; lab used the happy path. | Fixed every item and wired `GoalLoopRunner` to compose `Sandbox` + `TraceLog` + `Hippocampus`. |

### Era 20 — Measuring efficiency

| ME | YOU |
|---|---|
| "measure out new design effiency" | Built `examples/measure_efficiency.py` returning real numbers (loop rounds/wall-time, compaction reduction, replay latency, sandbox overhead). Removed a fabricated token-savings metric. |

### Era 21 — Efficiency recorded

| ME | YOU |
|---|---|
| (No further correction.) | Recorded measured results in `doc/02_goal_loop/efficiency.md`: 2 rounds / ~1.2s; compaction 98.75% reduction; replay ~0.6ms; sandbox ~5% overhead. |

---

## How this project teaches vibe coding with AI

### The human's job

- **Decide scope by dropping a spec.** The `goal-persistence` skill + course outline let the AI infer the build target without a step-by-step command. *(Era 1)*
- **Ask the "wait, how?" question.** "No LLM, how does this work?" forced a separation-of-concerns explanation and a real demo. *(Era 7)*
- **Give a process, not just an outcome.** The five-step plan → self-critic → implement → self-test → journey directive forced the work to be falsified before being trusted. *(Era 9)*
- **Reject false "done" with specifics.** Two reviews listed concrete defects, each of which the AI then fixed. *(Era 14, Era 19)*

### The AI's job

- **Build the smallest falsifiable unit first.** Status machine + store before runtime sugar, so transition bugs surfaced early. *(Era 3)*
- **Report failures with evidence, not hand-waving.** "16 passed, 4 failed" with exact symptoms. *(Era 4)*
- **Lock the interpretation before building.** "Goal harness" became a falsifiable target: the loop layer on top of persistence, not a rewrite. *(Era 10, Era 11)*
- **Self-criticize with a concrete diff.** Plan and implementation were each revised against a named list of defects. *(Era 11, Era 12)*
- **Accept a hard review as new evidence.** The earlier "complete" was a false positive; re-opening on the review turned a state-machine draft into a real harness. *(Era 14)*
- **Compose, don't just coexist.** The "six parallel toys" review forced real wiring (loop → sandbox → trace → hippocampus), proven by test, not prose. *(Era 19)*

### Portable rules

1. **A harness owns state, budget, and loop control; the model owns inference.** 20 tests pass with zero LLM calls. *(Eras 3–7)*
2. **State-machine transitions must be unit-tested, not eyeballed.** 4 of 20 tests validate allowed/forbidden transitions. *(Era 4)*
3. **Completion must be machine-grounded, not maker-claimed.** Only an independent checker verdict plus verified commands can finish. *(Era 12)*
4. **Self-critique finds what self-test then proves.** Bugs caught by re-reading the code against the core's semantics, then pinned by tests. *(Era 12, Era 13)*
5. **"Green tests" prove only what the tests exercise.** The first green was on stub maker/checker; the review made the gap concrete. *(Era 14)*
6. **"Layers exist" is not "layers compose."** The second review forced real wiring, proven by a composition test. *(Era 19)*
7. **Measure with real numbers, not injected constants.** A fabricated token-saving metric was caught and removed; the final report states what each number proves. *(Era 20)*

### One-sentence takeaway

**The human supplies the spec, the process, and the hard review; the AI builds falsifiable components, reports failures honestly, and lets failing tests and rejected "done" verdicts force the design to actually compose — rather than settling for a passing happy path.**
