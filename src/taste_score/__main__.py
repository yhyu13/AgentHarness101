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

from taste_score.amendments import ratify, suggest_amendments
from taste_score.gate import TasteGate
from taste_score.models import Probe, ProbeRun
from taste_score.mutator import Mutator
from taste_score.source import build_initial_probes
from taste_score.trace import TraceabilityVerifier

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


def build_constitution_verify(constitution: object) -> object:
    """Evidence-derived verify backed by the real constitution (anti-self-report)."""
    return TraceabilityVerifier(constitution)


def rank(
    agents: dict[str, object],
    golden: list[Probe],
    mutants: list[Probe],
    *,
    verify: object | None = None,
    pinned_digest: str | None = None,
) -> dict:
    """Run the gate and return a serializeable ranking from the TasteScores."""
    verify = verify if verify is not None else build_demo_verify()
    gate = TasteGate(pinned_digest=pinned_digest)
    scores = gate.score(agents, golden=golden, mutants=mutants, verify=verify)
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
    constitution: object | None = None,
) -> int:
    golden = build_initial_probes(constitution=constitution)
    mutator = Mutator()
    score_accum = []
    rows: list[dict] = []
    verify = build_constitution_verify(constitution) if constitution is not None else None
    pinned = constitution.digest() if constitution is not None else None
    for night in range(nights):
        nseed = seed + night
        menu = [mutator.mutate(p, nseed + i) for i in range(mutants_n) for p in golden[:3]]
        result = rank(
            build_demo_agents(), golden=golden, mutants=menu,
            verify=verify, pinned_digest=pinned,
        )
        result["night"] = night
        result["seed"] = nseed
        score_accum.append(result)
        rows.extend(result["ranking"])

    ledger: dict = {"nights": score_accum}
    if constitution is not None:
        # Pin the ruler so a tampered constitution can't be scored, and surface the
        # separate, evidence-grounded improvement phase + the per-principle compliance
        # matrix (paper L7) so the constitution layer is visible in the score.
        ledger["constitution_digest"] = constitution.digest()
        ledger["traceability"] = verify.matrix()
        amendments = suggest_amendments(
            [{"agent": r["agent"], "probe": "", "rejected": r["rejected"],
              "reason": r["reason"]} for r in rows]
        )
        ledger["amendments"] = [
            {"principle_id": a.principle_id, "action": a.action, "detail": a.detail,
             "evidence": list(a.evidence), "ratified": ratify(a)}
            for a in amendments
        ]

    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m taste_score", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    comp = sub.add_parser("compete", help="score agents and write the ledger")
    comp.add_argument("--nights", type=int, default=1)
    comp.add_argument("--mutants", type=int, default=3)
    comp.add_argument("--seed", type=int, default=421)
    comp.add_argument("--out", default=str(LEDGER))
    comp.add_argument(
        "--constitution",
        default=None,
        help="path to a constitution.toml; pins it as the ruler and enables traceability verify",
    )
    comp.set_defaults(fn=compete)

    args = parser.parse_args(argv)
    if args.command == "compete" and args.constitution:
        from taste_score.constitution import load_constitution

        constitution = load_constitution(Path(args.constitution))
        code = args.fn(args.nights, args.mutants, args.seed, args.out, constitution=constitution)
    else:
        code = args.fn(args.nights, args.mutants, args.seed, args.out)
    print(f"wrote nightly taste-score ledger to {args.out}")
    return code


if __name__ == "__main__":  # pragma: no cover - exercised via the console invocation
    raise SystemExit(main())
