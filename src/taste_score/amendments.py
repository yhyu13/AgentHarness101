"""Continuous-improvement loop (CSDD spec Block 5 / paper §6.4).

The nightly competition must *improve* the constitution, not just measure it. But
whoever is scored must not be the one rewriting the ruler. So this module is the
separate, evidence-grounded improvement phase: propose amendments citing the ledger
rows that justify them, and gate each proposal behind a ratifier (regression veto +
human approval for MUST-level changes). The proposal is authored from evidence; the
ratification is separate from any competing agent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Amendment:
    principle_id: str
    action: str  # tighten_pattern | narrow_violations | add_cwe
    detail: str
    evidence: tuple[str, ...]  # ledger row ids justifying this proposal


def suggest_amendments(rows: list[dict]) -> list[Amendment]:
    """From vetoed boundary-regression rows, propose tightening each principle.

    Evidence-grounded: it never invents a principle, only proposes to close a
    boundary that was actually conceded. Dedupes by principle id.
    """
    out: list[Amendment] = []
    seen: set[str] = set()
    for row in rows:
        if not row.get("rejected"):
            continue
        pid = row.get("probe")
        if pid and pid not in seen and "safety boundary" in (row.get("reason") or ""):
            seen.add(pid)
            out.append(
                Amendment(
                    principle_id=pid,
                    action="tighten_pattern",
                    detail=f"tighten {pid} pattern to close the conceded boundary",
                    evidence=(f"{row['agent']}:{pid}",),
                )
            )
    return out


def ratify(
    amendment: Amendment,
    *,
    require_human: bool = False,
    regress: Callable[[str], list[str]] | None = None,
) -> bool:
    """A non-self-serving gate on an amendment.

    A regression veto refuses it outright; MUST-level tightening still needs a
    human approval (``require_human``). Returns True only when it may be folded
    in — never by the agent being scored.
    """
    if regress is not None and regress(amendment.principle_id):
        return False  # regression veto
    if require_human and amendment.action == "tighten_pattern":
        return False  # MUST-level change needs human sign-off
    return True
