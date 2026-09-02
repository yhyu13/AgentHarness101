"""Layer-M6.5 taste score — a Goodhart-resistant measure of harness quality.

Taste = how well a harness run sits on the capability/safety frontier:
LLM 头脑 (C) + 手脚能力拓边 (E) + 安全边界 (S). Judged holistically, pairwise,
resists score-gaming via mutation of the eval menu and a held-out golden set.

Public surface mirrors the anti-gaming contract in
doc/superpowers/specs/2026-09-02-taste-score-design.md.
"""

from taste_score.gate import TasteGate, TasteScore
from taste_score.judge import PairwiseJudge, PairwiseVerdict
from taste_score.models import Probe, ProbeRun
from taste_score.mutator import Mutator

__all__ = [
    "Probe",
    "ProbeRun",
    "PairwiseJudge",
    "PairwiseVerdict",
    "Mutator",
    "TasteGate",
    "TasteScore",
]
