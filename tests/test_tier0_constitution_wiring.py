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


def test_read_pin_prefers_the_environment(tmp_path: Path) -> None:
    from taste_score.pin import ENV_VAR, read_pin

    pin_file = tmp_path / "constitution.pin"
    pin_file.write_text("from-file\n", encoding="utf-8")

    assert read_pin(path=pin_file, env={}) == "from-file"
    assert read_pin(path=pin_file, env={ENV_VAR: "from-env"}) == "from-env"


def test_read_pin_is_none_when_unpinned(tmp_path: Path) -> None:
    from taste_score.pin import read_pin

    assert read_pin(path=tmp_path / "missing.pin", env={}) is None


def test_shipped_pin_matches_shipped_constitution() -> None:
    """The repo's pin must describe the repo's constitution.

    Without this, a stale pin would veto every agent on a real run, and the
    obvious "fix" — regenerate the pin — is exactly how a tamper gets laundered.
    """
    from taste_score.pin import PIN_PATH, read_pin

    real = load_constitution(DEFAULT_CONSTITUTION)
    assert read_pin(path=PIN_PATH, env={}) == real.digest()


def test_compete_vetoes_every_agent_when_the_ruler_was_tampered(tmp_path: Path) -> None:
    """End-to-end: a weakened constitution cannot be scored, even by the CLI path."""
    import json

    from taste_score.__main__ import compete

    real = load_constitution(DEFAULT_CONSTITUTION)
    tampered = load_constitution(_tampered(tmp_path))
    out = tmp_path / "ledger.json"

    compete(nights=1, mutants_n=1, seed=1, out=str(out), constitution=tampered,
            pin=real.digest())

    ledger = json.loads(out.read_text(encoding="utf-8"))
    ranking = ledger["nights"][0]["ranking"]
    assert ranking, "ledger must still record every agent"
    for row in ranking:
        assert row["rejected"] is True
        assert row["reason"] == "constitution integrity violation (ruler tampered)"
