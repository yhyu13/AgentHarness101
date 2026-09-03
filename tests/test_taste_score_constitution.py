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


def test_constitution_digest_changes_when_principle_content_changes() -> None:
    # Lock 6 ("禁改尺子") must catch a ruler tamper at the CONTENT level, not only when
    # a principle is added/removed/renamed. The digest hashes the full principle payload;
    # otherwise an agent could weaken a `violations`/`pattern` sentinel IN PLACE (same id,
    # same version) and the pinned digest would still match — so the gate would NOT veto a
    # ruler that was silently weakened to score itself "safe" on code that actually has a
    # violation. That is the inside-the-ruler Goodhart move Lock 6 exists to stop.
    from taste_score.constitution import Constitution, Principle

    def mk(violations: str) -> Constitution:
        return Constitution(
            version="1.0.0",
            principles=(
                Principle(id="SEC-01", boundary="sandbox 文件写隔离", cwe="CWE-22",
                          level="MUST", constraint="白名单判定",
                          anchor="src/sandbox/path_policy.py",
                          pattern="allows_write", violations=violations, rationale="r"),
            ),
        )

    strict = mk("write_text\\(|open\\([^)]*['\"]w")
    weakened = mk("THIS_NEVER_MATCHES")  # same id/version, only the sentinel changed
    assert strict.digest() != weakened.digest()


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


def test_every_anchor_resolves_to_a_tracked_git_file() -> None:
    # Root cause of the "invented security domain" hole: a principle can anchor a
    # security guard that only the author has in their *working tree* (a ghost anchor).
    # ``test_every_anchor_resolves_and_matches_pattern`` above only checks ``exists()``
    # on disk, so it passes for a file that was never committed — but a fresh checkout
    # loses the guard, and the whole traceability layer would report it as missing.
    #
    # Pin the invariant: every anchor must be TRACKED by git, so the committed tree is
    # self-consistent and the traceability evidence is reproducible from the commit.
    import subprocess

    c = load_constitution(DEFAULT_CONSTITUTION)
    repo = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
    )
    if repo.returncode != 0:
        import pytest

        pytest.skip("not a git checkout — cannot verify anchor tracking")
    tracked = {line.strip().replace("\\", "/") for line in repo.stdout.splitlines()}
    for p in c.principles:
        rel = p.anchor.replace("\\", "/")
        assert rel in tracked, (
            f"{p.id} anchors {p.anchor!r} which is NOT tracked by git — a fresh "
            f"checkout would lose the guard (ghost anchor / invented security domain)"
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


def test_sandbox_env_scrub_boundary_is_constitutional() -> None:
    # The sandbox scrubs the child-process environment (_SAFE_ENV_KEYS + _safe_env())
    # so API keys/tokens held by the parent agent never leak into a sandboxed subprocess.
    # This is a REAL security guard (CWE-526) and must be pinned by a constitution
    # principle; otherwise an agent that removes the scrub would not register as a
    # safety regression — it would score clean.
    from taste_score.constitution import load_constitution, DEFAULT_CONSTITUTION

    c = load_constitution(DEFAULT_CONSTITUTION)
    p = next((p for p in c.principles if p.id == "SEC-06"), None)
    assert p is not None, "SEC-06 must pin the sandbox environment-scrub boundary"
    assert p.anchor == "src/sandbox/sandbox.py"
    assert p.cwe.startswith("CWE-")
    anchor = ROOT / p.anchor
    assert anchor.exists()
    text = anchor.read_text(encoding="utf-8")
    assert re.search(p.pattern, text), "SEC-06 pattern must exist in the anchor"
    assert not re.search(p.violations, text), "SEC-06 violations sentinel must be absent"


def test_command_verifier_safe_shell_boundary_is_constitutional() -> None:
    # SEC-04 pins the ALLOWLIST gate (which commands are permitted). SEC-07 pins a
    # distinct layer of the same CWE-78 surface: the SAFE EXECUTION FORM. The
    # goal_loop CommandVerifier must run the command via argv/shell=False so shell
    # metacharacters cannot smuggle an extra command. An agent could keep the
    # allowlist intact yet regress this to shell=True/os.system — a real CWE-78
    # regression SEC-04 cannot see (command_policy.py would be unchanged). It must
    # be pinned; otherwise that regression would score clean.
    from taste_score.constitution import load_constitution, DEFAULT_CONSTITUTION

    c = load_constitution(DEFAULT_CONSTITUTION)
    p = next((p for p in c.principles if p.id == "SEC-07"), None)
    assert p is not None, "SEC-07 must pin the CommandVerifier shell=False safe-execution boundary"
    assert p.anchor == "src/goal_loop/verifier.py"
    assert p.cwe.startswith("CWE-")
    anchor = ROOT / p.anchor
    assert anchor.exists()
    text = anchor.read_text(encoding="utf-8")
    assert re.search(p.pattern, text), "SEC-07 pattern must exist in the anchor"
    assert not re.search(p.violations, text), "SEC-07 violations sentinel must be absent"


def test_sandbox_fail_closed_execution_boundary_is_constitutional() -> None:
    # SEC-04 pins the CommandPolicy ALLOWLIST *decision* (a pure helper that sandbox.py
    # does not even import). SEC-06 pins only the environment scrub. NEITHER pins the
    # actual execution launch point in Sandbox.run — where the fail-closed default-deny
    # (refuse when no allowlist is configured), the runtime allowlist enforcement, and
    # the shell=False argv launch actually live. If an agent regressed Sandbox.run to
    # default-permit (drop the SANDBOX_UNAVAILABLE refuse) or to shell=True, no existing
    # principle would register it. It must be pinned; otherwise that safety regression
    # would score clean.
    from taste_score.constitution import load_constitution, DEFAULT_CONSTITUTION

    c = load_constitution(DEFAULT_CONSTITUTION)
    p = next((p for p in c.principles if p.id == "SEC-08"), None)
    assert p is not None, "SEC-08 must pin the Sandbox fail-closed execution floor"
    assert p.anchor == "src/sandbox/sandbox.py"
    assert p.cwe.startswith("CWE-")
    anchor = ROOT / p.anchor
    assert anchor.exists()
    text = anchor.read_text(encoding="utf-8")
    assert re.search(p.pattern, text), "SEC-08 pattern must exist in the anchor"
    assert not re.search(p.violations, text), "SEC-08 violations sentinel must be absent"


def test_llm_judge_fail_closed_boundary_is_constitutional() -> None:
    # SEC-08 pins the EXECUTION-layer fail-closed floor (Sandbox denies when no
    # allowlist). SEC-09 pins a DISTINCT layer of the same CWE-703 surface: the
    # EVALUATION boundary. The LLMJudge must fail closed — any error, timeout, or
    # unparseable reply is a FAIL, never an accidental PASS. A judge that swallows a
    # dead LLM and passes would let a bad result through the gate, and no existing
    # principle (all anchor sandbox/safety/verifier/injection) would register it. It
    # must be pinned; otherwise that safety regression would score clean.
    from taste_score.constitution import load_constitution, DEFAULT_CONSTITUTION

    c = load_constitution(DEFAULT_CONSTITUTION)
    p = next((p for p in c.principles if p.id == "SEC-09"), None)
    assert p is not None, "SEC-09 must pin the LLMJudge fail-closed evaluation boundary"
    assert p.anchor == "src/eval_harness/judge.py"
    assert p.cwe.startswith("CWE-")
    anchor = ROOT / p.anchor
    assert anchor.exists()
    text = anchor.read_text(encoding="utf-8")
    assert re.search(p.pattern, text), "SEC-09 pattern must exist in the anchor"
    assert not re.search(p.violations, text), "SEC-09 violations sentinel must be absent"


def test_tool_registry_least_privilege_boundary_is_constitutional() -> None:
    # The ToolRegistry.call enforces least privilege: a tool must not run unless its
    # permission is explicitly enabled, and a handler exception fails closed (ok=False,
    # never swallowed as ok=True). registered_roles.py routes maker/checker through this
    # permission gate, so it IS the live authorization boundary for tool calls. No
    # existing principle anchors tool_registry — SEC-04/05/07/08 pin command/injection/
    # execution layers, not the tool-call authorization gate. An agent that removes the
    # `permission not in self._enabled` gate (or inverts it to `in`) or swallows a
    # handler error as ok=True would score clean. It must be pinned; otherwise that
    # authorization regression goes unregistered.
    from taste_score.constitution import load_constitution, DEFAULT_CONSTITUTION

    c = load_constitution(DEFAULT_CONSTITUTION)
    p = next((p for p in c.principles if p.id == "SEC-10"), None)
    assert p is not None, "SEC-10 must pin the ToolRegistry least-privilege authorization boundary"
    assert p.anchor == "src/tool_registry/registry.py"
    assert p.cwe.startswith("CWE-")
    anchor = ROOT / p.anchor
    assert anchor.exists()
    text = anchor.read_text(encoding="utf-8")
    assert re.search(p.pattern, text), "SEC-10 pattern must exist in the anchor"
    assert not re.search(p.violations, text), "SEC-10 violations sentinel must be absent"


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
