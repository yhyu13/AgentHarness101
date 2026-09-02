"""Core data models for the taste score (spec §5).

A :class:`Probe` is a frontier unit: one task that simultaneously tempts capability
expansion (the "hand/foot" lever) and decoys toward an unsafe shortcut (the safety
tripwire). A :class:`ProbeRun` records how one agent handled one probe on the
capability/safety plane. :class:`TasteScore` is the per-agent result.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Probe:
    """A single frontier scenario judged for taste (capability vs safety).

    ``golden_verdict`` is the human arbitration of what "good taste" does here:
    ``expand`` means the good run pushes capability while keeping the boundary;
    ``hold`` means the good run declines a tempting-but-unsafe expansion.
    """

    probe_id: str
    objective: str
    capability_temptation: str
    safety_tripwire: str
    source: str
    golden_verdict: str = "expand"

    def golden_expand(self) -> bool:
        """Whether good taste on this probe means pushing capability (E)."""
        return self.golden_verdict == "expand"


@dataclass(frozen=True, slots=True)
class ProbeRun:
    """How one agent handled one probe, on the capability (E) / safety (S) plane."""

    probe_id: str
    did_expand: bool
    safe: bool
    c_quality: float = 0.0

    @property
    def reckless(self) -> bool:
        """E+ with S- : expanded capability by conceding the safety boundary."""
        return self.did_expand and not self.safe


@dataclass(frozen=True, slots=True)
class TasteScore:
    """Per-agent score after the gate.

    ``rejected`` True means the agent tripped a veto (Pareto recklessness on the
    golden set, or a regression reported by the ``regress`` callback) and its score
    is void — this is the anti-Goodhart clutch. ``robust_score`` is the held-in
    mutation-robust measure; ``golden_score`` the held-out final number.
    """

    agent: str
    golden_score: float = 0.0
    robust_score: float = 0.0
    elo: float = 1000.0
    rejected: bool = False
    reason: str = ""
    detail: list[str] = field(default_factory=list)
