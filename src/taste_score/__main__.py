"""``python -m taste_score compete`` — the nightly multi-agent competition (spec §7).

Builds the golden probe set, mutates it into the night's menu, ranks a set of agents
through the anti-Goodhart gate, and appends the result to the ledger. This wires the
loop so several agents can be scored against the capability/safety frontier each night;
only a monotonic golden-set improvement is worth recording.

Example:
    python -m taste_score compete --golden 12 --mutants 3 --seed 421
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from taste_score.gate import TasteGate
from taste_score.models import Probe, ProbeRun
from taste_score.mutator import Mutator
from taste_score.source import build_initial_probes

LEDGER = Path(__file__).resolve().parent / "ledger.json"


def build_demo_agents() -> dict[str, object]:
    """Three demo agents: robust (real taste), reckless (expands by conceding safety),
    and liar (claims an expansion that never happened). Kept so the CLI is self-contained."""
    return {
        "robust": lambda p: ProbeRun(p.probe_id, did_expand=True, safe=True),
        "reckless": lambda p: ProbeRun(p.probe_id, did_expand=True, safe=False),
        "liar": lambda p: ProbeRun(p.probe_id, did_expand=True, safe=True),
    }


def build_demo_verify() -> object:
    """Evidence-derived runs — a liar self-reports expand+safe, but the evidence shows
    nothing was actually expanded, so ``did_expand`` is False (anti-self-report)."""

    def verify(name: str, probe: Probe) -> ProbeRun:
        if name == "reckless":
            return ProbeRun(probe.probe_id, did_expand=True, safe=False)
        if name == "liar":
            return ProbeRun(probe.probe_id, did_expand=False, safe=True)  # did nothing
        return ProbeRun(probe.probe_id, did_expand=True, safe=True)

    return verify


def rank(agents: dict[str, object], golden: list[Probe], mutants: list[Probe]) -> dict:
    """Run the gate and return a serializeable ranking from the TasteScores."""
    scores = TasteGate().score(agents, golden=golden, mutants=mutants, verify=build_demo_verify())
    ranking = [
        {
            "agent": name,
            "golden_score": round(s.golden_score, 3),
            "robust_score": round(s.robust_score, 3),
            "elo": round(s.elo, 1),
            "rejected": s.rejected,
            "reason": s.reason,
        }
        for name, s in sorted(scores.items(), key=lambda kv: -kv[1].golden_score)
    ]
    return {"ranking": ranking}


def compete(
    nights: int,
    mutants_n: int,
    seed: int,
    out: str,
) -> int:
    golden = build_initial_probes()
    mutator = Mutator()
    score_accum = []
    for night in range(nights):
        nseed = seed + night
        menu = [mutator.mutate(p, nseed + i) for i in range(mutants_n) for p in golden[:3]]
        result = rank(build_demo_agents(), golden=golden, mutants=menu)
        result["night"] = night
        result["seed"] = nseed
        score_accum.append(result)

    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"nights": score_accum}, indent=2), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m taste_score", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    comp = sub.add_parser("compete", help="score agents and write the ledger")
    comp.add_argument("--nights", type=int, default=1)
    comp.add_argument("--mutants", type=int, default=3)
    comp.add_argument("--seed", type=int, default=421)
    comp.add_argument("--out", default=str(LEDGER))
    comp.set_defaults(fn=compete)

    args = parser.parse_args(argv)
    code = args.fn(args.nights, args.mutants, args.seed, args.out)
    print(f"wrote nightly taste-score ledger to {args.out}")
    return code


if __name__ == "__main__":  # pragma: no cover - exercised via the console invocation
    raise SystemExit(main())
