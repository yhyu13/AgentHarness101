"""Static traceability verifier (CSDD spec + paper L7).

This is the anti-self-report resolver: instead of trusting an agent's claimed
``did_expand``/``safe``, it derives them from real evidence in ``src/``. Each
constitution principle maps to an ``anchor`` file (with a ``pattern`` that must be
present and a ``violations`` sentinel that must be absent). Deterministic, no LLM.
"""

from __future__ import annotations

import re
from pathlib import Path

from taste_score.constitution import Constitution
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
        anchor = Path(p.anchor)
        text = anchor.read_text(encoding="utf-8") if anchor.exists() else ""
        expanded = bool(anchor.exists() and re.search(p.pattern, text))
        safe = not re.search(p.violations, text)
        return ProbeRun(probe.probe_id, did_expand=expanded, safe=safe)
