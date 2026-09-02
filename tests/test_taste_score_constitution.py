"""Tests for the versioned security constitution (CSDD integration, spec 2026-09-02).

A constitution is the explicit, hash-addressable form of the safety boundary S.
These tests pin: (a) it parses from the packaged TOML, (b) its digest is a stable
content hash, (c) every principle traces to a REAL src/ file (authoring rule: no
invented security domains), and (d) a correct anchor contains the pattern AND does
not contain the violations sentinel.
"""

from __future__ import annotations

from pathlib import Path
import re

from taste_score.constitution import DEFAULT_CONSTITUTION, Principle, load_constitution

ROOT = Path(__file__).resolve().parents[1]


def test_load_constitution_reads_principles() -> None:
    c = load_constitution(DEFAULT_CONSTITUTION)
    assert c.version == "1.0.0"
    assert c.principles, "constitution must define principles"
    assert all(isinstance(p, Principle) for p in c.principles)
    assert all(p.level in ("MUST", "SHOULD", "MAY") for p in c.principles)
    assert all(p.cwe.startswith("CWE-") for p in c.principles)


def test_constitution_digest_is_stable_content_hash() -> None:
    c = load_constitution(DEFAULT_CONSTITUTION)
    assert c.digest() == c.digest()  # stable across calls
    assert len(c.digest()) == 64  # sha256 hex


def test_constitution_digest_changes_when_version_changes() -> None:
    import tomllib
    from taste_score.constitution import _from_payload
    a = load_constitution(DEFAULT_CONSTITUTION)
    payload = tomllib.loads(DEFAULT_CONSTITUTION.read_text(encoding="utf-8"))
    payload["version"] = "2.0.0"
    b = _from_payload(payload)
    assert a.digest() != b.digest()


def test_every_anchor_resolves_and_matches_pattern() -> None:
    # Authoring rule: a constitution principle must trace to a REAL src/ file that
    # actually contains its implementation pattern — no invented security domains.
    c = load_constitution(DEFAULT_CONSTITUTION)
    for p in c.principles:
        anchor = ROOT / p.anchor
        assert anchor.exists(), f"{p.id} anchor missing: {p.anchor}"
        text = anchor.read_text(encoding="utf-8")
        assert re.search(p.pattern, text), f"{p.id} pattern not found in {p.anchor}: {p.pattern}"
        assert not re.search(p.violations, text), (
            f"{p.id} violations sentinel already present in {p.anchor}: {p.violations}"
        )


def test_traceability_matrix_reports_per_principle_evidence(tmp_path: Path) -> None:
    # The score's CSDD layer must expose, per principle, the anchor + pattern +
    # whether the implementation evidence is present (did_expand) and clean (safe).
    from taste_score.constitution import Constitution
    from taste_score.trace import TraceabilityVerifier

    ok = tmp_path / "guard.py"
    ok.write_text("def allow(path):\n    return True\n", encoding="utf-8")
    princ = Principle(id="SEC-01", boundary="sandbox 文件写隔离", cwe="CWE-22",
                      level="MUST", constraint="白名单判定", anchor=str(ok),
                      pattern="def allow", violations="write_text", rationale="r")
    const = Constitution(version="1.0.0", principles=(princ,))
    rows = TraceabilityVerifier(const).matrix()
    assert rows and rows[0]["id"] == "SEC-01"
    assert rows[0]["anchor"] == str(ok)
    assert rows[0]["pattern"] == "def allow"
    assert rows[0]["expanded"] is True   # anchor contains the pattern
    assert rows[0]["safe"] is True       # no violation sentinel
    assert "level" in rows[0] and "boundary" in rows[0]

    # A principle backed by a missing anchor reports no evidence.
    princ2 = Principle(id="SEC-02", boundary="高危拦截", cwe="CWE-306", level="MUST",
                       constraint="c", anchor=str(tmp_path / "missing.py"),
                       pattern="guard", violations="exec", rationale="r")
    const2 = Constitution(version="1.0.0", principles=(princ2,))
    rows2 = TraceabilityVerifier(const2).matrix()
    assert rows2[0]["expanded"] is False and rows2[0]["safe"] is False


def test_compliance_score_tracks_each_principle_implementation(tmp_path: Path) -> None:
    # The single-agent CSDD score: fraction of principles BOTH implemented and clean.
    # Each modification that installs a guard or removes a violation raises it; any
    # violation or missing guard drops it. This is what "each modification adds points"
    # measures.
    from taste_score.constitution import Constitution
    from taste_score.trace import TraceabilityVerifier

    guard = tmp_path / "guard.py"
    guard.write_text("def allow(path):\n    return True\n", encoding="utf-8")
    princ = Principle(id="SEC-01", boundary="文件写隔离", cwe="CWE-22", level="MUST",
                      constraint="白名单", anchor=str(guard), pattern="def allow",
                      violations="write_text", rationale="r")
    const = Constitution(version="1.0.0", principles=(princ,))
    v = TraceabilityVerifier(const)
    # Fully compliant -> 1.0 (both installed and clean).
    assert abs(v.compliance() - 1.0) < 1e-9
    # Introduce a violation (guard now writes to any path) -> safe drops -> 0.0.
    guard.write_text("def allow(path):\n    write_text(path)\n", encoding="utf-8")
    assert v.compliance() == 0.0
    # Remove the guard entirely -> not implemented -> 0.0.
    guard.write_text("pass\n", encoding="utf-8")
    assert v.compliance() == 0.0
    # Empty constitution -> no principles, no credit.
    empty = Constitution(version="1.0.0", principles=())
    assert TraceabilityVerifier(empty).compliance() == 0.0
