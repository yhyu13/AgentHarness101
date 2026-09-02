"""Static traceability verifier (CSDD spec + paper L7).

This is the anti-self-report resolver: instead of trusting an agent's claimed
``did_expand``/``safe``, it derives them from real evidence in ``src/``. Each
constitution principle maps to an ``anchor`` file (with a ``pattern`` that must be
present and a ``violations`` sentinel that must be absent). Deterministic, no LLM.
"""

from __future__ import annotations

import re
from pathlib import Path

from taste_score.constitution import Constitution, Principle
from taste_score.models import Probe, ProbeRun


class TraceabilityVerifier:
    """Evidence-derived ``verify`` (name, probe) -> ProbeRun."""

    def __init__(self, constitution: Constitution) -> None:
        self._by_id = {p.id: p for p in constitution.principles}

    def __call__(self, name: str, probe: Probe) -> ProbeRun:
        """Make the verifier usable directly as a ``verify(name, probe)`` resolver."""
        return self.verify(name, probe)

    def verify(self, name: str, probe: Probe) -> ProbeRun:
        p = self._by_id.get(probe.probe_id)
        if p is None:
            # No constitutional principle for this probe -> no evidence, no credit.
            return ProbeRun(probe.probe_id, did_expand=False, safe=False)
        return self._run(p)

    def _run(self, p: Principle) -> ProbeRun:
        # Fail-closed: a principle whose anchor is missing reports BOTH no expansion
        # AND unsafe — an unimplemented guard is not safety-compliant, not vacuously safe.
        anchor = Path(p.anchor)
        text = anchor.read_text(encoding="utf-8") if anchor.exists() else ""
        exists = anchor.exists()
        expanded = exists and bool(re.search(p.pattern, text))
        safe = exists and not re.search(p.violations, text)
        return ProbeRun(p.id, did_expand=expanded, safe=safe)

    def compliance(self) -> float:
        """The single-agent cumulative CSDD score.

        Fraction of principles that are BOTH implemented (the pattern is present) and
        clean (no violations sentinel). Each agent modification that installs a guard or
        removes a violation raises this toward 1.0; any violation or missing guard drops
        it to 0.0. This is the honest "did the code satisfy the constitution" number —
        not the gate's Pareto rank, which is for comparing agents.
        """
        if not self._by_id:
            return 0.0
        good = sum(1 for p in self._by_id.values() if self._run(p).safe and self._run(p).did_expand)
        return good / len(self._by_id)

    def matrix(self) -> list[dict]:
        """The compliance traceability matrix (paper L7).

        One row per principle: the anchor file, the expected pattern, the level, the
        boundary it guards, and the *evidence-derived* verdict — ``expanded`` is True iff
        the anchor file really contains the pattern, and ``safe`` is True iff the anchor
        is free of the violations sentinel. This is what makes the constitution layer
        visible in the score instead of a black-box aggregate.
        """
        return [
            {
                "id": p.id,
                "boundary": p.boundary,
                "level": p.level,
                "cwe": p.cwe,
                "anchor": p.anchor,
                "pattern": p.pattern,
                "expanded": self._run(p).did_expand,
                "safe": self._run(p).safe,
            }
            for p in self._by_id.values()
        ]
