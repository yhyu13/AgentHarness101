# Harness Efficiency — Measured

This doc records the actual numbers from `examples/measure_efficiency.py`, so
"efficient" is backed by evidence rather than vibes.

## How to reproduce

```bash
py -3 examples/measure_efficiency.py
```

It writes `examples/efficiency_report.json` and prints the same JSON.

## What it measures (and what it does not)

Each number comes from the component actually running, not from a constant the script
feeds back to itself:

| Dimension | Real signal | What it proves |
|---|---|---|
| Loop | rounds, maker calls, wall-clock to `complete`, criteria satisfied | The loop converges to verified completion in a bounded number of incremental rounds |
| Context compaction | chars in vs. chars kept + summary | The 80% cutoff materially shrinks context while preserving marked items |
| Hippocampus memory | replay/retrospective wall time + hit counts | Long-term memory is retrievable in microseconds |
| Sandbox | allowlisted executor vs. raw subprocess time | The safety layer adds near-zero overhead |

It deliberately does **not** invent a token count: token accounting is a caller-supplied
fact, so printing a script-injected "tokens saved" would be fabricated. Where tokens
are real (the LLM demo), they are already reported in `README.md`.

## Latest measured results

```text
loop.rounds               = 2
loop.wall_seconds         ≈ 1.2
loop.criteria_satisfied   = [a, b]

compaction.chars_in       = 48,550
compaction.chars_out      = 609
compaction.reduction_ratio= 0.0125   (98.75% reduction)
compaction.kept_items     = 10 (important, verbatim)
compaction.archived_items = 90

memory.replay_seconds     ≈ 0.0006
memory.important_lines    = 5
memory.correct_facts      = 6

sandbox.overhead_ratio    ≈ 1.05    (5% overhead vs raw subprocess)
```

## Reading the numbers

- **Loop**: two incremental rounds to verified completion — the maker is not redoing
  all work each round, and the independent checker + machine verification confirm the
  end state rather than trusting self-report.
- **Compaction**: crossing the 80% window collapses 48.5 KB of noisy transcript into
  609 characters while keeping the 10 marked items verbatim. The reduction is the
  efficiency gain; the kept items are the safety guarantee.
- **Memory**: replay of a 5-step trajectory plus retrospective returns in ~0.6 ms,
  meaning the memory layer is effectively free to consult on every turn.
- **Sandbox**: 5% overhead for allowlist + `shell=False` + timeout on top of a raw
  subprocess. The fail-closed contract costs almost nothing.

## What would make this stronger

1. Run the loop against a real LLM and report *actual* token usage (needs credentials).
2. Sweep the window size to show the compaction ratio holds as context grows.
3. Measure the loop with a pathological maker that never makes progress, to bound the
   blocked path.

These are explicit next steps, not claims of things that are already true.
