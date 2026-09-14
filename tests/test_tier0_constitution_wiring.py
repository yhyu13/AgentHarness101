"""Tier-0 wiring: the four CSDD locks must be reachable from the real CLI path.

Spec: doc/superpowers/specs/2026-09-14-tier0-csdd-wiring-and-bugfixes-design.md
Before this task, ``rank()`` dropped the constitution on the floor, so
``gate.py``'s Lock-6 branch (which requires ``constitution is not None``) was
unreachable dead code and a tampered ruler vetoed nobody.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taste_score.__main__ import build_demo_agents, rank
from taste_score.constitution import DEFAULT_CONSTITUTION, load_constitution
from taste_score.pin import ENV_VAR, read_pin
from taste_score.source import build_initial_probes


@pytest.fixture(autouse=True)
def _no_ambient_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Normalize ``read_pin()``'s fallback so ``--pin`` is the only free variable.

    ``read_pin()`` resolves env -> ``constitution.pin`` -> ``None``, and
    ``AH_CONSTITUTION_PIN`` is the documented first-choice entry point
    (``__main__.py``'s ``--help``). Leave it set and the fallback stops being the
    repo's honest digest -- which flips the two CLI tests below into passing through
    the environment instead of through the flag, so they survive a
    ``pin=args.pin -> pin=None`` mutation. Clearing it here makes the fallback land
    on the repo's ``constitution.pin``, which
    ``test_shipped_pin_matches_shipped_constitution`` pins to the honest digest.
    """
    monkeypatch.delenv(ENV_VAR, raising=False)


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
    """End-to-end: a weakened constitution cannot be scored."""
    import json

    from taste_score.__main__ import compete

    real = load_constitution(DEFAULT_CONSTITUTION)
    tampered = load_constitution(_tampered(tmp_path))
    out = tmp_path / "ledger.json"

    compete(nights=1, mutants_n=1, seed=1, out=str(out), constitution=tampered, pin=real.digest())

    ledger = json.loads(out.read_text(encoding="utf-8"))
    ranking = ledger["nights"][0]["ranking"]
    assert ranking, "ledger must still record every agent"
    for row in ranking:
        assert row["rejected"] is True
        assert row["reason"] == "constitution integrity violation (ruler tampered)"


def _run_cli(constitution_path: Path, pin: str, out: Path) -> list[dict]:
    """Drive ``main()`` as the operator would and return the ledger's ranking rows."""
    import json

    from taste_score.__main__ import main

    code = main(
        [
            "compete",
            "--constitution",
            str(constitution_path),
            "--pin",
            pin,
            "--out",
            str(out),
            "--nights",
            "1",
            "--mutants",
            "1",
            "--seed",
            "1",
        ]
    )
    assert code == 0
    return json.loads(out.read_text(encoding="utf-8"))["nights"][0]["ranking"]


def test_cli_pin_flag_vetoes_a_ruler_the_pin_does_not_name(tmp_path: Path) -> None:
    """End-to-end through ``main()``: a ``--pin`` holding a digest no ruler has vetoes
    the run, even though the constitution on disk is the honest one.

    A pin is an opaque expected digest, not a path -- ``gate.py`` never resolves it,
    it only compares it to ``constitution.digest()`` -- so this sentinel vetoes every
    agent. Drop ``--pin`` in ``main()`` and the ``read_pin()`` fallback takes over:
    with the ambient env cleared by ``_no_ambient_pin`` that fallback is the honest
    digest, the veto never fires, and the assertions below fail. Pinning the *honest*
    digest reaches the same verdict through the fallback, so it cannot tell the flag
    apart from it; the test below walks the opposite direction instead.
    """
    real = load_constitution(DEFAULT_CONSTITUTION)
    wrong_pin = "0" * 64
    assert wrong_pin != real.digest(), "fixture is stale: the sentinel is a real digest"
    # The discrimination above rests on the fallback being the honest digest; state it
    # so that if it ever stops holding (a pin exported past the fixture, a rewritten
    # constitution.pin) this fails loudly here instead of quietly passing below.
    assert read_pin() == real.digest(), "fallback pin is not the honest digest"

    ranking = _run_cli(DEFAULT_CONSTITUTION, wrong_pin, tmp_path / "ledger.json")

    assert ranking, "ledger must still record every agent"
    for row in ranking:
        assert row["rejected"] is True
        assert row["reason"] == "constitution integrity violation (ruler tampered)"


def test_cli_pin_flag_is_what_the_ruler_is_compared_against(tmp_path: Path) -> None:
    """The mirror image: pinning the *tampered* digest makes that same weakened file
    scoreable again, because the veto compares the loaded digest against ``--pin``
    rather than against the repo's ``constitution.pin``.

    Dropping ``--pin`` in ``main()`` fails this test too: whatever the fallback hands
    back, the tampered file no longer matches it, so every agent comes back vetoed and
    the assertion below fails. The two tests pin the two directions; neither is
    redundant.
    """
    tampered_path = _tampered(tmp_path)
    tampered = load_constitution(tampered_path)

    ranking = _run_cli(tampered_path, tampered.digest(), tmp_path / "ledger.json")

    assert ranking, "ledger must still record every agent"
    reasons = [row["reason"] for row in ranking]
    assert "constitution integrity violation (ruler tampered)" not in reasons, reasons


def test_pareto_veto_reports_the_probe_that_was_conceded() -> None:
    real = load_constitution(DEFAULT_CONSTITUTION)
    golden = build_initial_probes(constitution=real)

    result = rank(
        build_demo_agents(),
        golden=golden,
        mutants=[],
        pinned_digest=real.digest(),
        constitution=real,
    )

    reckless = next(r for r in result["ranking"] if r["agent"] == "reckless")
    assert reckless["rejected"] is True
    assert reckless["rejected_probe"], "the conceded probe id must survive to the ledger"


def test_compete_proposes_amendments_from_real_rejections(tmp_path: Path) -> None:
    """The improvement loop was dead: compete() hardcoded probe="" so the
    amendments list was always empty."""
    import json

    from taste_score.__main__ import compete

    real = load_constitution(DEFAULT_CONSTITUTION)
    out = tmp_path / "ledger.json"

    compete(nights=1, mutants_n=1, seed=1, out=str(out), constitution=real, pin=real.digest())

    ledger = json.loads(out.read_text(encoding="utf-8"))
    assert ledger["amendments"], "a conceded safety boundary must produce a proposal"
    for amendment in ledger["amendments"]:
        assert amendment["principle_id"]
        assert amendment["action"] == "tighten_pattern"


def test_rank_vetoes_an_agent_that_trips_a_regression() -> None:
    real = load_constitution(DEFAULT_CONSTITUTION)
    golden = build_initial_probes(constitution=real)

    def regress(name: str) -> list[str]:
        return ["sandbox"] if name == "robust" else []

    result = rank(
        build_demo_agents(),
        golden=golden,
        mutants=[],
        pinned_digest=real.digest(),
        constitution=real,
        regress=regress,
    )

    by_agent = {r["agent"]: r for r in result["ranking"]}
    assert by_agent["robust"]["rejected"] is True
    assert by_agent["robust"]["reason"] == "regression: sandbox"


def test_compete_forwards_a_regression_callback(tmp_path: Path) -> None:
    import json

    from taste_score.__main__ import compete

    real = load_constitution(DEFAULT_CONSTITUTION)
    out = tmp_path / "ledger.json"

    def regress(name: str) -> list[str]:
        return ["red-line"] if name == "liar" else []

    compete(
        nights=1,
        mutants_n=1,
        seed=1,
        out=str(out),
        constitution=real,
        pin=real.digest(),
        regress=regress,
    )

    ledger = json.loads(out.read_text(encoding="utf-8"))
    liar = next(r for r in ledger["nights"][0]["ranking"] if r["agent"] == "liar")
    assert liar["reason"] == "regression: red-line"
