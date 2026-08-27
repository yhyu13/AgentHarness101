# Plan — Migrate the Goal Harness (Goal Loop) into AgentHarness101

**Date:** 2026-08-27
**Source repo:** `D:\GitRepo-AI\learn-harness-engineering`
**Target repo:** `D:\GitRepo-AI\AgentHarness101` (this repo)

---

## 1. Objective

Migrate the **goal harness** from `learn-harness-engineering` into this repo as a
runnable, tested Python package that composes with the existing
`goal_persistence` package, and document the whole build in a JOURNEY file.

## 2. What "goal harness" means here (scope decision)

The source repo's "goal harness" is the `/goal` loop from Lecture 13
(`lecture-13-loop-engineering`) and its hands-on form in Project 07
(`project-07-loop-engineering-first-loop`). Its concrete, migratable artifacts are:

| Source artifact | What it encodes |
|---|---|
| `docs/en/lectures/lecture-13-loop-engineering/code/goal-template.md` | Goal definition: objective, acceptance criteria, scope (fair game / hands off), verification method, stop conditions, how-to-work |
| `docs/en/lectures/lecture-13-loop-engineering/code/loop-state-template.md` | Loop state: round log, cumulative stats, blocker list, final result |
| `docs/en/lectures/lecture-13-loop-engineering/code/maker-prompt.md` | Maker role (implement + basic self-verify) |
| `docs/en/lectures/lecture-13-loop-engineering/code/checker-prompt.md` | Checker role (independent verify, find faults with evidence, verdict) |
| Lecture 13 body | Generator/evaluator separation, `/goal` = goal + verification + stop condition, four silent costs, maturity ladder |
| Project 07 body | Goal loop → timer loop → maker-checker loop; loop state management |

The source does **not** contain a literal runnable "goal harness" file; it contains the
**design and templates** for one. This repo already contains `goal_persistence/` (the
durable "goal sticks across turns" layer, documented in
`doc/01_goal_persistence/journey.md`). The migration therefore adds the missing **loop
layer on top of `goal_persistence`**.

### In scope

1. A `goal_loop/` Python package that turns a `GoalSpec` + a maker + a checker into a
   self-running, durable, verifiable loop.
2. Ported templates (`goal.md`, `loop-state.md`, `maker-prompt.md`,
   `checker-prompt.md`) as usable reference files.
3. Composition with `goal_persistence.GoalRuntime` so the loop is durable, anti-drift,
   and budget-limited.
4. Tests, a runnable demo, and this plan.

### Out of scope (deliberately)

- The timer loop (`/loop`) and cloud/event-driven scheduling. This migration is only the
  **goal** loop, per the task wording.
- A real LLM backend. The loop proves its state machine with pluggable
  maker/checker callables, exactly like `goal_persistence` proves itself without a model.
- Migrating the Electron/TypeScript project scaffolding. This repo is a Python course;
  we port the *semantics*, not the runtime.

## 3. Target design

### Package layout

```text
goal_loop/
  __init__.py        # public API
  models.py          # GoalSpec, AcceptanceCriterion, Scope, StopCondition,
                     # RoundRecord, LoopState, Verdict, MakerOutput, CheckerOutput
  verifier.py        # CommandVerifier + VerificationResult
  roles.py           # Maker/Checker Protocol + a trivial example pair
  loop_runner.py     # GoalLoopRunner: orchestrates the loop, composes GoalRuntime
  templates/
    goal.md          # ported goal-template
    loop-state.md    # ported loop-state-template
    maker-prompt.md  # ported maker-prompt
    checker-prompt.md# ported checker-prompt
tests/
  test_goal_loop.py  # new tests
goal_loop_demo.py    # end-to-end demo
```

### Core abstractions

#### `models.py`

- `AcceptanceCriterion` — one machine-checkable "done" condition: `id`,
  `description`, and an optional `verify_command` (the command whose exit 0 proves it).
- `Scope` — `fair_game: list[str]`, `hands_off: list[str]` (human-authored, advisory to
  the maker; the runner does not enforce filesystem access).
- `StopCondition` — `kind` + `value`; kinds: `max_rounds`, `budget_tokens`,
  `budget_wall_ms`. `budget_*` kinds are derived from the underlying
  `goal_persistence` goal and need no separate value. Completion is the inherent success
  rule (not a stop condition), and the blocked audit is owned by `goal_persistence`'s
  fixed three-strike rule (not a spec-level stop condition).
- `GoalSpec` — the whole goal description: `objective`, `acceptance_criteria`,
  `scope`, `stop_conditions`, `how_to_work`. Validation rejects a spec with no
  acceptance criteria or an empty objective.
- `Verdict` — enum `PASS`, `FAIL`, `ACCEPT_WITH_MINOR`.
- `Issue` — `severity` (`critical|medium|minor`), `location`, `description`, `evidence`,
  `suggestion` (ported from checker-prompt output requirements).
- `RoundRecord` — number, started/finished timestamps, maker summary, checker verdict
  and issues, verification results, next-round plan, human-intervention flag.
- `LoopState` — `loop_name`, `started_at`, `current_round`, `status`, `rounds`,
  `blockers`, cumulative stats (rounds/passed/failed/issues/interventions/files), and a
  `final_result` (`status`, `finished_at`, `summary`). Ported from `loop-state-template.md`.
- `MakerOutput` — `summary`, `modified_files`, `self_verification`, `risks`.
- `CheckerOutput` — `verdict`, `issues`, `command_results` (machine results, not claims).

#### `verifier.py`

- `CommandVerifier.run(command: str, timeout_s: int = 60) -> VerificationResult`
- Runs via `subprocess.run(command, shell=False)` — the command is treated as a single
  executable name (e.g. `python`, `pytest`), not a shell string. This keeps the trust
  boundary explicit and avoids shell injection from command text.
- Captures `returncode`, `stdout`, `stderr` (tail-truncated), and `timed_out`. Returns
  structured evidence; never a bare boolean.
- `VerificationResult.ok` is `returncode == 0 and not timed_out`.

#### `roles.py`

- `Maker` and `Checker` are `typing.Protocol`s; the runner is model-agnostic.
- **Generator/evaluator separation is structural**: the runner only trusts
  `CheckerOutput` for the round verdict. `MakerOutput.self_verification` is recorded but
  never used to decide completion.
- Provide `EchoMaker` (returns a fixed summary) and `AlwaysPassChecker` / configurable
  `StaticChecker` as trivial examples for the demo and tests.

#### `loop_runner.py`

- `GoalLoopRunner(goal_spec, runtime, maker, checker, state_dir=None)`.
- `run()` loop, one round per iteration:
  1. Evaluate stop conditions before doing work; stop early on `max_rounds` / budget.
  2. Build the anti-drift steering context from the underlying `goal_persistence` goal
     (via `runtime.maybe_continue(thread_id)`); it must still be active.
  3. `maker(spec, state)` → `MakerOutput`.
  4. `checker(spec, maker_output)` → `CheckerOutput` (independent verdict).
  5. Run each acceptance criterion's `verify_command` through `CommandVerifier`; a
     criterion is satisfied only if its command exits 0 (or, when it has no command, it
     is confirmed by the checker's PASS/ACCEPT verdict).
  6. Append a `RoundRecord`, update `LoopState` stats/blockers, persist state to disk.
  7. Apply round usage to the underlying `GoalRuntime` (token/wall budget auto-transition).
  8. Decide continue vs. stop: stop on `max_rounds`, budget terminal, or blocker
     threshold; **complete only** when every acceptance criterion is verified satisfied
     AND the checker verdict is PASS (or ACCEPT_WITH_MINOR with all criteria passing).
- **Completion evidence**: the runner calls `runtime.mark_complete(thread_id, evidence)`
  where `evidence` is a compact, machine-derived string of the pass verdict + the list
  of verified criteria + verification command return codes. No completion without that.
- **Blocked**: three consecutive rounds with no new progress (checker FAIL and no
  criteria newly satisfied) → `runtime.mark_blocked(...)` three times, which flips the
  underlying goal to `GoalStatus.BLOCKED` via the existing three-strike rule. A round
  with any new criterion satisfied resets the no-progress streak.

### Composition with `goal_persistence`

- `GoalLoopRunner` owns a `goal_persistence.GoalRuntime`. The loop's objective, usage,
  budget, anti-drift contract, and blocked/completion audits are durable across restarts.
- Loop state (rounds) is a separate disk file (`<state_dir>/<thread_id>.loop_state.json`),
  keeping "what is the goal" (SQLite row) and "how far along" (loop state) separate,
  matching the source's split between goal and loop-state templates.

## 4. Verification strategy (self-test)

New `tests/test_goal_loop.py` must cover:

1. `GoalSpec` validates (rejects empty objective and zero acceptance criteria).
2. `CommandVerifier` reports pass and fail with evidence; times out a hung command.
3. `LoopState` accumulates round stats and blocker list correctly.
4. `GoalLoopRunner` completes and marks the underlying goal `complete` with evidence when
   the checker passes and all criteria verify.
5. `GoalLoopRunner` stops after `max_rounds` without falsely declaring completion.
6. `GoalLoopRunner` blocks after three consecutive no-progress rounds.
7. Structural separation: the loop does **not** complete when only the maker
   self-reports success but the checker verdict is FAIL.
8. Budget auto-transition from `goal_persistence` still fires through the loop.

Existing `tests/test_harness.py` (20 tests) must remain green.

Commands:

```bash
py -3 -m pytest tests/test_goal_loop.py tests/test_harness.py -q
py -3 goal_loop_demo.py
```

## 5. Acceptance criteria

- [ ] `goal_loop/` package exists and imports cleanly.
- [ ] Four templates are present and reflect the source semantics.
- [ ] `py -3 -m pytest tests/test_goal_loop.py tests/test_harness.py -q` → all pass.
- [ ] `py -3 goal_loop_demo.py` runs a goal loop to completion with evidence.
- [ ] `goal_persistence` remains unchanged and its 20 tests stay green.
- [ ] `doc/02_goal_loop/journey.md` documents the migration (final step).

## 6. Risks and tradeoffs

| Risk | Mitigation |
|---|---|
| Over-engineering the loop into a framework | Thin state machine: `GoalSpec` → maker → checker → verify → state → repeat. No scheduler, no plugin system. |
| Subprocess safety | Commands come from a human-authored `GoalSpec`, run shell-less (`shell=False`) with timeout; trust boundary documented in the module docstring. |
| Misreading "goal harness" as something else | Section 2 locks the interpretation explicitly; the user can correct at plan review. |
| Diverging from source semantics | Templates ported close-to-verbatim; the runner mirrors the goal/verification/stop-condition trio and maker/checker split. |

## 7. Self-critique of the first draft

What changed between draft 1 and this revision:

- **Cut `VerificationMethod` as a separate abstraction.** It duplicated what
  `AcceptanceCriterion.verify_command` already carries; the ordered list of steps becomes
  a plain `list[AcceptanceCriterion]` on `GoalSpec`. Less surface, same semantics.
- **Made verification machine-grounded, not maker/checker-claimed.** Completion now
  requires each criterion's command to exit 0 (or an explicit checker PASS for
  command-less criteria). This removes the "feels about right" loophole the source
  explicitly warns against ("verification debt").
- **Fixed the completion-evidence definition.** Draft 1 said "with evidence" vaguely; it
  now names the exact evidence string the runner builds.
- **Removed the `ExampleMaker`/`Checker` naming ambiguity** and settled on `EchoMaker` +
  `StaticChecker` with an explicit configurable verdict.
- **Removed `FileWritingMaker`.** It implied the demo would touch the filesystem, which
  muddies a state-machine test. The demo stays in-memory with echo/static roles.
- **Clarified the blocked rule** by reusing `goal_persistence`'s three-strike mechanism
  and defining "no progress" precisely (checker FAIL + no new criterion satisfied).

## 8. Relationship to the earlier `doc/02_goal_harness` plan

An earlier, interrupted attempt left a plan in `doc/02_goal_harness/PLAN.md`. That plan's
four milestones map directly onto this one:

- **M1 (parse `goal.md`)** → this plan's `GoalSpec.from_markdown` (now implemented).
- **M2 (driver + independent checker)** → this plan's `GoalLoopRunner` + maker/checker
  protocol split.
- **M3 (human-readable round log)** → this plan's `LoopState` persisted to disk (JSON;
  the source's `loop-state.md` stays a human template, while the machine writes typed
  round records).
- **M4 (course wiring: lecture/lab/outline/README)** → this plan's acceptance criteria
  and `doc/02_goal_loop/lecture.md` + `lab.md`.

The prior plan's two "待确认" (open questions) were resolved here without user input:
(1) the loop stops at `active` when `max_rounds` is hit, returning a loop-level
`stopped_max_rounds` state rather than inventing a new `GoalStatus`; (2) the checker is a
pluggable callable, with a real subprocess `CommandVerifier` for machine criteria.
