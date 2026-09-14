# Taste Engine Waterline — next genuine improvements (2026-09-03)

> Date: 2026-09-03. Status: self-grilled + self-answered → drafted exec plan, awaiting
> approval on the ONE security-tradeoff decision (Phase 0) before implementation.
> Context: `taste_score` engine is at CSDD=1.0 (saturated) and 301 passed/56 skipped.
> Per `quality-benchmark-design`: saturation is a defect in the MEASURE, not a win —
> the honest fix is a non-saturable dimension (verifier mutation-score) plus hardening
> the locks that are presently narrative rather than structurally enforced.

---

## Why this exists

The engine's own metric drove S to a ceiling. The remaining genuine headroom is not
"raise the number" (it's maxed) — it's make the anti-Goodhart machinery *provably* robust
and *provably* non-gameable, and add the one dimension that cannot saturate: the strength
of the verifier/guard itself (measured by mutation score).

## The one decision the user must make (Phase 0)

**Menu evidence policy** — a real security tradeoff (per repo rule: security tradeoffs are
user-only calls). The committed design is `自述不可信` (fail-closed); the uncommitted
in-flight change trusts the agent's self-report on unanchored probes. Two honest choices:

- **RECOMMENDED (A, fail-closed + anchor the menu):** on a probe with no verifier evidence,
  the gate returns `(did_expand=False, safe=False)` — a liar gets NO credit, period. To keep
  mutation robustness from going vacuous (all robust_score 0), build the mutation menu from
  **constitution-anchored probes** (SEC-0x), where the verifier always has real `src/`
  evidence. Result: robust_score discriminates ON REAL EVIDENCE, and self-report stays
  never-trusted. This restores lock 1 and makes lock 2 real.
- Alternative (B, trust self-report on the menu): preserves discriminating robust_score, but a
  liar gains credit on unanchored probes → re-opens the hole lock 1 exists to close. Not
  recommended; it is the current uncommitted behavior and it contradicts gate.py's own docstring.

## Ideas (each anchored to a verified code gap)

| # | Idea | Gap (file:line) | Verdict |
|---|------|-----------------|---------|
| B | Fix menu evidence policy (fail-closed + anchor menu) | gate.py:29,66-75 | KEEP, #1 |
| A | Verifier mutation-score (non-saturable dimension) | no verifier-strength metric exists | KEEP, #2 |
| E | Adversarial E2E: prove a real cheater is rejected | only lambda demo agents | KEEP, #3 |
| C | Truly held-out golden set (lock 3) | compete mutates golden[:3] into menu | KEEP, #4 |
| D | Mutator swaps the scaffold, not just words (lock 2) | mutator.py:17-49 | KEEP, #5 |
| G | verify wire-check (anchor actually referenced) | trace.py regex-only | PARK (follow-up) |
| F | Per-night budget cap (lock 5) | narrative only | PARK (low value here) |

## Exec plan (one phase = one honest improvement = one cron fire)

Each phase is spec→plan→TDD (AGENTS.md), red-green, full-suite + coverage gate, commit only
if a real check improved and nothing regressed, never push.

### Phase 0 — settle the menu evidence policy (decision above)
Direction from user. Straightforward once chosen.

### Phase 1 — B: restore fail-closed + anchor the mutation menu
- Red: `test_gate_fail_closed_when_verify_has_no_evidence` — raw TraceabilityVerifier as verify,
  a liar on an unanchored probe must NOT be credited (`did_expand=False, safe=False`).
  `test_mutation_menu_anchored_discriminates` — a menu built from SEC-0x probes yields a
  non-zero, differing robust_score across agents on real evidence.
- Green: gate.py revert the fallback (`return agents[name](probe)` → `ProbeRun(...,False,False)`);
  complete() builds the menu from constitution-anchored probes; fix the test that currently
  asserts self-report credit.

### Phase 2 — A: verifier mutation-score
- Red: `test_verifier_mutation_score.py` — inject N defect mutants into the guard sources
  (drop a pattern keyword, weaken a violation, stub the guard), assert the verifier/gate
  rejects the correct fraction; <1.0 = asserted as honest headroom (non-saturable).
- Green: `src/taste_score/mutation_score.py` (+ surface in ledger/report), deterministic,
  no LLM, table-driven.

### Phase 3 — E: adversarial E2E harness
- Red: `test_adversarial_agent.py` — a LiarAgent (writes a dead stub, self-reports expand+safe)
  and a RecklessAgent (removes a guard to speed up) run through the full `compete`; assert
  both are rejected with real measured numbers (not lambda outcomes).

### Phase 4 — C: held-out golden set
- Red: `test_golden_set_held_out.py` — the golden probes used for the final verdict never
  appear in the mutation menu; a memorizer of the working probe family is not rewarded.
- Green: add `src/taste_score/golden.json` (hand-written, human-judged) + wire into compete;
  exclude it from the menu.

### Phase 5 — D: scaffold-swapping mutator
- Red: `test_mutator_changes_scaffold.py` — mutation changes objective/temptation/tripwire
  (the whole challenge), not just wording; a path-memorizer fails the new scaffold.
- Green: mutator.py pulls from a larger scenario pool and swaps the scaffold deterministically.

## Acceptance (every phase)
- `python3 -m pytest -q` green (>= current baseline + new), coverage `scripts/check.sh`
  (fail_under=92), `ruff check` clean, per-package gate (taste_score >= 70%).
- Each idea lands only with a red-green regression test (fails before, passes after).
- The gate is never used to raise a saturated number; each improvement is structural.

## Out of scope
- Full AST/semgrep verify (spec "Option C") — Phases 1-5 above, then reconsider G.
- OS-level seccomp/Landlock (Windows-degraded to PathPolicy).
