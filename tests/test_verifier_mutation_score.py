"""Verifier mutation-score: the non-saturable measure of the engine's own anti-cheat.

csdd_score saturates at 1.0 once every principle is implemented+clean. The honest
non-saturable counter is the VERIFIER's strength: how much of a cheater's fake guard it
refuses to bless. The naive regex core cannot yet tell a dead stub or a comment-only
pattern from a real guard, so the score is honestly <1.0 — that gap is the point.
"""

from pathlib import Path
import ast
import re

from taste_score.constitution import DEFAULT_CONSTITUTION, Constitution, load_constitution
from taste_score.mutation_score import mutant_cases, verifier_strength
from taste_score.trace import TraceabilityVerifier, _is_dead_stub


def _constitution() -> Constitution:
    return load_constitution(DEFAULT_CONSTITUTION)


def test_verifier_strength_is_bounded_and_honestly_unsaturated() -> None:
    """Valid fraction AND a real, non-saturable gap (a fake guard is currently blessed)."""
    s = verifier_strength(_constitution())
    assert 0.0 <= s <= 1.0
    # Honest, non-saturable headroom: the naive regex cannot yet catch every fake, so this
    # must NOT be 1.0. If it ever hits 1.0, ADD a subtler mutant (e.g. a nested/partial
    # guard) rather than celebrating — that's the non-saturation dynamic.
    assert s < 1.0


def test_mutant_cases_cover_the_fake_guard_moves() -> None:
    """Every principle gets the stub / comment-only / absent fake-guard cases, none genuine."""
    for p in _constitution().principles:
        labels = {c.label for c in mutant_cases(p)}
        assert {"stub", "comment", "absent"} <= labels
        assert all(not c.expected_genuine for c in mutant_cases(p))


def test_absent_guard_is_not_blessed_as_an_expansion() -> None:
    """An absent guard must never read as a genuine safe expansion (did_expand=False)."""
    p = _constitution().principles[0]
    absent = next(c for c in mutant_cases(p) if c.label == "absent")
    run = TraceabilityVerifier.classify(p.pattern, p.violations, absent.text, p.id)
    assert run.did_expand is False


def test_classify_core_is_pure_and_deterministic() -> None:
    """Same input -> same ProbeRun; the core has no file/state dependence."""
    p = _constitution().principles[0]
    a = TraceabilityVerifier.classify(p.pattern, p.violations, "class X:\n pass\n", "p")
    b = TraceabilityVerifier.classify(p.pattern, p.violations, "class X:\n pass\n", "p")
    assert a == b


def test_classify_rejects_dead_stub_guard() -> None:
    """A cheater ships ``class <guard>: pass`` — the naive regex blessed that as a real
    expansion (did_expand=True, safe=True). A hardened verifier must refuse to bless a
    placeholder shell that carries the symbol but has no logic behind it."""
    p = _constitution().principles[1]  # SEC-02 pattern 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    run = TraceabilityVerifier.classify(
        p.pattern, p.violations, "class SafetyGuard:\n    pass\n", p.id
    )
    assert run.did_expand is False


def test_classify_rejects_comment_only_guard() -> None:
    """A symbol that appears ONLY inside a comment is not an implementation. The naive
    regex counted ``# allows_write`` as a genuine expansion; the hardened verifier must not."""
    p = _constitution().principles[0]  # SEC-01 pattern 'allows_write|_is_within|allow_roots'
    run = TraceabilityVerifier.classify(p.pattern, p.violations, "# allows_write\n", p.id)
    assert run.did_expand is False


def test_classify_rejects_docstring_only_stub() -> None:
    """A class whose body is only a docstring + ``pass`` is still a shell — the symbol is
    present but there is no logic. The hardening must reject it as a dead stub too."""
    p = _constitution().principles[1]  # SEC-02 pattern 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    run = TraceabilityVerifier.classify(
        p.pattern, p.violations, 'class SafetyGuard:\n    """no logic"""\n    pass\n', p.id
    )
    assert run.did_expand is False


def test_classify_still_blesses_a_real_guard() -> None:
    """Hardening must NOT over-reject: a symbol present AND backed by real logic still reads
    as a genuine safe expansion. This guards against tightening into a false-negative on a
    genuinely implemented guard."""
    p = _constitution().principles[1]  # SEC-02 pattern 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    real = (
        "class SafetyGuard:\n"
        "    _HIGH_RISK_ACTIONS = ('rm', 'format')\n"
        "    def check(self, action):\n"
        "        return action in self._HIGH_RISK_ACTIONS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, real, p.id)
    assert run.did_expand is True
    assert run.safe is True


def test_hardened_verifier_still_sees_every_constitution_anchor_as_compliant() -> None:
    """The hardening must NOT over-reject a real guard: every genuine constitution anchor (a
    real ``src/`` file with real logic) still reads as implemented (did_expand) AND clean
    (safe) — i.e. csdd stays 1.0 after tightening. This is the false-negative guard."""
    for p in _constitution().principles:
        anchor = Path(p.anchor)
        assert anchor.exists(), f"{p.id} anchor missing: {p.anchor}"
        text = anchor.read_text(encoding="utf-8")
        run = TraceabilityVerifier.classify(p.pattern, p.violations, text, p.id)
        assert run.did_expand is True, f"{p.id} lost its expansion after hardening"
        assert run.safe is True, f"{p.id} reads as unsafe after hardening"


def test_stub_mutants_are_valid_python() -> None:
    """The mutation-score's ``stub`` fake must model a REAL dead stub — valid Python that
    carries the guard's name with no logic behind it. A generator that emits ``class class
    Guard: pass`` (invalid) is a MEASUREMENT BUG: the verifier's parse-error fallback then
    blesses an impossible fake, deflating the honest verifier strength. Every stub must
    parse."""
    for p in _constitution().principles:
        for case in mutant_cases(p):
            if case.label != "stub":
                continue
            assert "stub" in case.label
            try:
                ast.parse(case.text)
            except SyntaxError as exc:  # pragma: no cover - red condition
                raise AssertionError(
                    f"{p.id} stub fake is not valid Python: {case.text!r} ({exc})"
                )


def test_verifier_rejects_nested_dead_stub() -> None:
    """A subtler fake: the guard class exists but is nested inside an unused wrapper whose
    body is only a ``pass`` — a top-level-only placeholder check blesses it, a recursive one
    must not. This is the design's own ``add a subtler mutant`` ratchet."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    nested = "def _unused():\n    class SafetyGuard:\n        pass\n"
    run = TraceabilityVerifier.classify(p.pattern, p.violations, nested, p.id)
    assert run.did_expand is False, "verifier must not bless a nested dead-stub shell"


def test_mutant_cases_include_partial_and_nested_fakes() -> None:
    """The non-saturation dynamics: once the dead/comment/absent fakes are caught, the fake
    set must grow with a *subtler* one (the design's 'add a subtler mutant' rule) so the score
    stays honestly <1.0. Every principle gets stub/comment/absent AND nested/partial."""
    for p in _constitution().principles:
        labels = {c.label for c in mutant_cases(p)}
        assert {"stub", "comment", "absent", "nested", "partial"} <= labels
        assert all(not c.expected_genuine for c in mutant_cases(p))


def test_partial_guard_is_real_code_but_inert() -> None:
    """The ``partial`` (inert) fake is the honest semantic ceiling: it carries the guard
    symbol AND real code, yet does nothing effective — a shape the verifier can only catch by
    semantics, not by regex/dead-stub. It must be valid Python, contain the pattern, and NOT
    read as a placeholder shell (so it genuinely models 'present-but-ineffective')."""
    for p in _constitution().principles:
        partial = next((c for c in mutant_cases(p) if c.label == "partial"), None)
        assert partial is not None, f"{p.id} missing the 'partial/inert' fake"
        assert not partial.expected_genuine
        ast.parse(partial.text)  # must be valid Python
        assert re.search(p.pattern, partial.text), (
            f"{p.id} partial fake must still carry the pattern, got {partial.text!r}"
        )
        assert not _is_dead_stub(partial.text), (
            f"{p.id} partial fake should carry real (inert) code, not be a shell"
        )
