"""Tier-0 wiring: the four CSDD locks must be reachable from the real CLI path.

Spec: doc/superpowers/specs/2026-09-14-tier0-csdd-wiring-and-bugfixes-design.md
Before this task, ``rank()`` dropped the constitution on the floor, so
``gate.py``'s Lock-6 branch (which requires ``constitution is not None``) was
unreachable dead code and a tampered ruler vetoed nobody.
"""

from __future__ import annotations

from pathlib import Path

from taste_score.__main__ import build_demo_agents, rank
from taste_score.constitution import DEFAULT_CONSTITUTION, load_constitution
from taste_score.source import build_initial_probes


def _tampered(tmp_path: Path) -> Path:
    """A copy of the shipped constitution with one MUST weakened to SHOULD."""
    original = DEFAULT_CONSTITUTION.read_text(encoding="utf-8")
    tampered = original.replace('level = "MUST"', 'level = "SHOULD"', 1)
    assert tampered != original, "fixture is stale: no MUST level found to weaken"
    dest = tmp_path / "constitution.toml"
    dest.write_text(tampered, encoding="utf-8")
    return dest


def test_rank_vetoes_every_agent_when_the_ruler_was_tampered(tmp_path: Path) -> None:
    real = load_constitution(DEFAULT_CONSTITUTION)
    tampered = load_constitution(_tampered(tmp_path))
    golden = build_initial_probes(constitution=real)

    result = rank(
        build_demo_agents(),
        golden=golden,
        mutants=[],
        pinned_digest=real.digest(),
        constitution=tampered,
    )

    rejected = {r["agent"]: r["reason"] for r in result["ranking"] if r["rejected"]}
    assert set(rejected) == {"robust", "reckless", "liar"}, rejected
    for reason in rejected.values():
        assert reason == "constitution integrity violation (ruler tampered)"


def test_rank_scores_normally_when_the_ruler_matches_the_pin(tmp_path: Path) -> None:
    real = load_constitution(DEFAULT_CONSTITUTION)
    golden = build_initial_probes(constitution=real)

    result = rank(
        build_demo_agents(),
        golden=golden,
        mutants=[],
        pinned_digest=real.digest(),
        constitution=real,
    )

    reasons = {r["agent"]: r["reason"] for r in result["ranking"] if r["rejected"]}
    assert "constitution integrity violation (ruler tampered)" not in reasons.values()
