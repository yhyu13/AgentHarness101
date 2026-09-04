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
                raise AssertionError(f"{p.id} stub fake is not valid Python: {case.text!r} ({exc})")


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


def test_classify_rejects_inert_passthrough_guard() -> None:
    """A cheater ships a guard that carries the symbol AND real code but always returns a
    constant and never inspects its inputs (``def allows_write: return True`` — always allow).
    The naive regex + dead-stub check blesses this as a genuine safe expansion; a hardened
    verifier must refuse to bless an *inert pass-through* guard. This is the always-allow
    cheat the mutation-score's ``partial`` fake models, and catching it is the honest verifier
    win (it is the difference between 'the symbol exists' and 'the guard actually decides')."""
    p = _constitution().principles[0]  # SEC-01 pattern 'allows_write|_is_within|allow_roots'
    # Always returns True, never reads path/self -> inert pass-through, not a real decision.
    inert = "def allows_write(self, path):\n    return True\n"
    run = TraceabilityVerifier.classify(p.pattern, p.violations, inert, p.id)
    assert run.did_expand is False, "verifier must not bless an always-allowing pass-through guard"
    # A constant-returning function that DOES branch on its inputs is a real decision, not inert.
    real = "def allows_write(self, path):\n    return path in self._allowed_roots\n"
    run2 = TraceabilityVerifier.classify(p.pattern, p.violations, real, p.id)
    assert run2.did_expand is True, "verifier must still bless a guard that decides on its inputs"
    assert run2.safe is True


def test_classify_rejects_inert_statement_forms() -> None:
    """The inert-guard hardening must also refuse the other pass-through shapes a cheater ships:
    an empty-symbol assignment (``allows_write = ()``), a class whose only method always returns
    a constant (``class SafetyGuard: def check: return True``), and a function that returns a
    constant after a dead ``if`` (``if x: pass; return True``). All carry the symbol + real code
    yet decide nothing."""
    # SEC-01 'allows_write|_is_within|allow_roots' -> bare method name assigned an empty tuple.
    p0 = _constitution().principles[0]
    r = TraceabilityVerifier.classify(p0.pattern, p0.violations, "allows_write = ()\n", p0.id)
    assert r.did_expand is False, "empty-symbol assignment is not a real guard"
    # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS' -> class whose only method returns a constant.
    p1 = _constitution().principles[1]
    r2 = TraceabilityVerifier.classify(
        p1.pattern,
        p1.violations,
        "class SafetyGuard:\n    def check(self, action):\n        return True\n",
        p1.id,
    )
    assert r2.did_expand is False, "a class whose only check always returns True is inert"
    # SEC-10 'permission not in self\\._enabled' -> a dead if + an unconditional constant return.
    p10 = _constitution().principles[10]
    r3 = TraceabilityVerifier.classify(
        p10.pattern,
        p10.violations,
        "def _guard():\n    if permission not in self._enabled:\n        pass\n    return True\n",
        p10.id,
    )
    assert r3.did_expand is False, "a function that always returns a constant is inert"


def test_verifier_still_blesses_a_real_branching_guard() -> None:
    """The inert-guard hardening must NOT over-reject a genuinely implemented guard that returns
    True in one branch and False in another — that is a real decision, not a pass-through. This
    is the false-negative guard for the 'all returns are constants' heuristic, which would
    otherwise flag a legitimate ``if x: return True; return False`` whitelist as inert."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    real = (
        "class SafetyGuard:\n"
        "    _HIGH_RISK_ACTIONS = ('rm', 'format')\n"
        "    def check(self, action):\n"
        "        if action in self._HIGH_RISK_ACTIONS:\n"
        "            return False\n"
        "        return True\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, real, p.id)
    assert run.did_expand is True, "verifier must bless a real branching whitelist guard"
    assert run.safe is True


def test_inert_vs_constant_hidden_and_helper_hidden_split_the_cheat_space() -> None:
    """After the helper-hidden hardening, the ``helper-hidden`` fake (a constant returned through a
    top-level HELPER CALL, ``return _always()``) is now REJECTED, and so — this fire — is
    ``attribute-hidden`` (a constant delegated through an ATTRIBUTE/METHOD call, ``return
    self._always()``), ``attr-value-hidden`` (a constant returned through a bare ATTRIBUTE VALUE,
    ``return self._ALWAYS``), and ``instance-attr-hidden`` (a constant returned through an instance
    ``attribute bound in ``__init__``) and, this fire, ``inst-attr-mutator-hidden`` (a constant
    returned through an instance attribute bound in a NON-``__init__`` mutator that the guard CALLS,
    ``self._setup()`` then ``return self._ALWAYS``) — the resolver now traces a mutator called in the
    same function that binds the attribute to a single provable constant. It also traces a factory that
    returns a fully-inert mutated instance (``factory-hidden``), a factory that DELEGATES to a
    base builder (``nested-factory-hidden``), AND a class-level factory METHOD (``static-factory-hidden``,
    ``_Helper.create().val``), following the factory chain to the constructor. The honest
    residual headroom moved one ratchet step deeper to ``classmethod-cls-factory-hidden`` (a constant
    reached through a ``@classmethod`` factory that builds via the ``cls`` receiver, ``_Helper.create()``
    doing ``h = cls()``, a runtime-parameter receiver the static analyzer cannot tie to a class). Each
    caught cheat level reveals a subtler still-unsolved one, so
    verifier_strength stays honestly < 1.0 — the non-saturation ratchet keeps firing."""
    for p in _constitution().principles:
        partial = next(c for c in mutant_cases(p) if c.label == "partial")
        run_p = TraceabilityVerifier.classify(p.pattern, p.violations, partial.text, p.id)
        assert run_p.did_expand is False, f"{p.id} partial/inert fake must be rejected"
        hidden = next(c for c in mutant_cases(p) if c.label == "constant-hidden")
        assert re.search(p.pattern, hidden.text), (
            f"{p.id} constant-hidden fake must carry the pattern, got {hidden.text!r}"
        )
        run_h = TraceabilityVerifier.classify(p.pattern, p.violations, hidden.text, p.id)
        assert run_h.did_expand is False, (
            f"{p.id} constant-hidden fake (return through a NAME) must now be rejected"
        )
        helper = next(c for c in mutant_cases(p) if c.label == "helper-hidden")
        assert re.search(p.pattern, helper.text), (
            f"{p.id} helper-hidden fake must carry the pattern, got {helper.text!r}"
        )
        ast.parse(helper.text)  # valid Python
        run_g = TraceabilityVerifier.classify(p.pattern, p.violations, helper.text, p.id)
        assert run_g.did_expand is False, (
            f"{p.id} helper-hidden fake (constant via a top-level HELPER CALL) must now be rejected"
        )
        attribute = next(c for c in mutant_cases(p) if c.label == "attribute-hidden")
        assert re.search(p.pattern, attribute.text), (
            f"{p.id} attribute-hidden fake must carry the pattern, got {attribute.text!r}"
        )
        ast.parse(attribute.text)  # valid Python
        run_a = TraceabilityVerifier.classify(p.pattern, p.violations, attribute.text, p.id)
        assert run_a.did_expand is False, (
            f"{p.id} attribute-hidden fake (constant via an ATTRIBUTE/METHOD call) must be rejected"
        )
        attr_value = next(c for c in mutant_cases(p) if c.label == "attr-value-hidden")
        assert re.search(p.pattern, attr_value.text), (
            f"{p.id} attr-value-hidden fake must carry the pattern, got {attr_value.text!r}"
        )
        ast.parse(attr_value.text)  # valid Python
        run_av = TraceabilityVerifier.classify(p.pattern, p.violations, attr_value.text, p.id)
        assert run_av.did_expand is False, (
            f"{p.id} attr-value-hidden fake (constant via a bare class-body attribute VALUE) "
            f"must now be rejected"
        )
        instance = next(c for c in mutant_cases(p) if c.label == "instance-attr-hidden")
        assert re.search(p.pattern, instance.text), (
            f"{p.id} instance-attr-hidden fake must carry the pattern, got {instance.text!r}"
        )
        ast.parse(instance.text)  # valid Python
        run_ins = TraceabilityVerifier.classify(p.pattern, p.violations, instance.text, p.id)
        assert run_ins.did_expand is False, (
            f"{p.id} instance-attr-hidden fake (constant via an __init__-bound instance attribute) "
            f"must now be rejected"
        )
        mutator = next(c for c in mutant_cases(p) if c.label == "inst-attr-mutator-hidden")
        assert re.search(p.pattern, mutator.text), (
            f"{p.id} inst-attr-mutator-hidden fake must carry the pattern, got {mutator.text!r}"
        )
        ast.parse(mutator.text)  # valid Python
        run_mut = TraceabilityVerifier.classify(p.pattern, p.violations, mutator.text, p.id)
        assert run_mut.did_expand is False, (
            f"{p.id} inst-attr-mutator-hidden fake (constant via a called mutator that binds a "
            f"provable single constant) must now be rejected"
        )
        factory = next(c for c in mutant_cases(p) if c.label == "factory-hidden")
        assert re.search(p.pattern, factory.text), (
            f"{p.id} factory-hidden fake must carry the pattern, got {factory.text!r}"
        )
        ast.parse(factory.text)  # valid Python
        run_factory = TraceabilityVerifier.classify(p.pattern, p.violations, factory.text, p.id)
        assert run_factory.did_expand is False, (
            f"{p.id} factory-hidden fake (constant reached through a factory function that returns "
            f"a fully-inert mutated instance) must now be rejected — the resolver traces a factory's "
            f"single statically-known return class and resolves the attribute constant through it"
        )
        nested_factory = next(c for c in mutant_cases(p) if c.label == "nested-factory-hidden")
        assert re.search(p.pattern, nested_factory.text), (
            f"{p.id} nested-factory-hidden fake must carry the pattern, got {nested_factory.text!r}"
        )
        ast.parse(nested_factory.text)  # valid Python
        run_nf = TraceabilityVerifier.classify(p.pattern, p.violations, nested_factory.text, p.id)
        assert run_nf.did_expand is False, (
            f"{p.id} nested-factory-hidden fake (constant reached through a factory that delegates "
            f"to ANOTHER builder) must now be rejected — the resolver follows a factory chain to the "
            f"base builder that directly constructs the class"
        )
        static_factory = next(c for c in mutant_cases(p) if c.label == "static-factory-hidden")
        assert re.search(p.pattern, static_factory.text), (
            f"{p.id} static-factory-hidden fake must carry the pattern, got {static_factory.text!r}"
        )
        ast.parse(static_factory.text)  # valid Python
        run_sf = TraceabilityVerifier.classify(p.pattern, p.violations, static_factory.text, p.id)
        assert run_sf.did_expand is False, (
            f"{p.id} static-factory-hidden fake (constant reached through a @staticmethod/classmethod "
            f"factory whose return class the resolver now traces) must now be rejected"
        )
        nested_sf = next(c for c in mutant_cases(p) if c.label == "nested-static-factory-hidden")
        assert re.search(p.pattern, nested_sf.text), (
            f"{p.id} nested-static-factory-hidden fake must carry the pattern, got {nested_sf.text!r}"
        )
        ast.parse(nested_sf.text)  # valid Python
        run_nsf = TraceabilityVerifier.classify(p.pattern, p.violations, nested_sf.text, p.id)
        assert run_nsf.did_expand is False, (
            f"{p.id} nested-static-factory-hidden fake (constant reached through a factory method that "
            f"delegates to another factory method) must now be rejected — the resolver follows the "
            f"method→method delegation chain to the base builder"
        )
        classmethod_sf = next(
            c for c in mutant_cases(p) if c.label == "classmethod-cls-factory-hidden"
        )
        assert re.search(p.pattern, classmethod_sf.text), (
            f"{p.id} classmethod-cls-factory-hidden fake must carry the pattern, got {classmethod_sf.text!r}"
        )
        ast.parse(classmethod_sf.text)  # valid Python
        run_cm = TraceabilityVerifier.classify(p.pattern, p.violations, classmethod_sf.text, p.id)
        assert run_cm.did_expand is False, (
            f"{p.id} classmethod-cls-factory-hidden fake (constant reached through a @classmethod factory "
            f"that builds via the cls receiver) must now be rejected — the resolver traces a classmethod "
            f"factory's ``cls()`` construction back to the receiver class"
        )
        nested_cm = next(
            c for c in mutant_cases(p) if c.label == "nested-classmethod-cls-factory-hidden"
        )
        assert re.search(p.pattern, nested_cm.text), (
            f"{p.id} nested-classmethod-cls-factory-hidden fake must carry the pattern, "
            f"got {nested_cm.text!r}"
        )
        ast.parse(nested_cm.text)  # valid Python
        run_ncm = TraceabilityVerifier.classify(p.pattern, p.violations, nested_cm.text, p.id)
        assert run_ncm.did_expand is False, (
            f"{p.id} nested-classmethod-cls-factory-hidden fake (constant reached through a classmethod "
            f"factory that DELEGATES to a sibling classmethod) must now be rejected — the resolver threads "
            f"the ``cls`` receiver through a classmethod→classmethod delegation chain to the base builder"
        )
        instance_cm = next(
            c for c in mutant_cases(p) if c.label == "classmethod-instance-receiver-hidden"
        )
        assert re.search(p.pattern, instance_cm.text), (
            f"{p.id} classmethod-instance-receiver-hidden fake must carry the pattern, "
            f"got {instance_cm.text!r}"
        )
        ast.parse(instance_cm.text)  # valid Python
        run_icm = TraceabilityVerifier.classify(p.pattern, p.violations, instance_cm.text, p.id)
        assert run_icm.did_expand is True, (
            f"{p.id} classmethod-instance-receiver-hidden fake (constant reached through a classmethod "
            f"factory called on an INSTANCE receiver, ``_Helper().create()``) is the new honest residual "
            f"headroom and must still bless"
        )


def test_verifier_rejects_helper_call_passthrough() -> None:
    """A cheater ships ``_always() -> True`` and a guard that delegates to it — the guard carries
    the symbol AND real code, inspects nothing, always returns True, yet the constant-return
    detector could not trace a CALL (only a NAME/literal). The hardened verifier must resolve a
    top-level helper call that always returns one constant and refuse to bless the pass-through."""
    p = _constitution().principles[0]  # SEC-01 'allows_write|_is_within|allow_roots'
    fake = (
        "def _always(self, path):\n"
        "    return True\n"
        "def allows_write(self, path):\n"
        "    return _always(self, path)\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, fake, p.id)
    assert run.did_expand is False, (
        "verifier must reject a guard that delegates to an always-constant helper"
    )


def test_verifier_still_blesses_helper_that_decides() -> None:
    """Hardening must NOT over-reject: a guard that delegates to a helper which DECIDES on its
    inputs (returns a non-constant like ``path in roots``) is a real guard, not a pass-through.
    Only a helper that provably always returns ONE constant is treated as inert."""
    p = _constitution().principles[0]  # SEC-01 'allows_write|_is_within|allow_roots'
    real = (
        "def _check(self, path):\n"
        "    return path in self._allowed_roots\n"
        "def allows_write(self, path):\n"
        "    return _check(self, path)\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, real, p.id)
    assert run.did_expand is True, "verifier must bless a guard that delegates to a deciding helper"
    assert run.safe is True


def test_verifier_rejects_attribute_call_passthrough() -> None:
    """A cheater ships an inert guard that delegates its constant through a METHOD call on the
    guard's own class (``self._always()``) — the symbol AND real code are present but the guard
    always returns the same constant without inspecting its inputs. The resolver now traces a bound
    method call into the method's constant, so the pass-through is flagged inert and NOT blessed."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def _always(self, action):\n"
        "        return True\n"
        "    def check(self, action):\n"
        "        return self._always(action)\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, "attribute/method-call constant must now be rejected as inert"


def test_verifier_still_blesses_method_that_decides_on_state() -> None:
    """Hardening must NOT over-reject: a method that delegates to ANOTHER method on ``self`` which
    DECIDES on its inputs (returns a non-constant like ``path in roots``) is a real guard, not a
    pass-through. Only a called method that provably always returns ONE constant is treated as inert."""
    p = _constitution().principles[0]  # SEC-01 'allows_write|_is_within|allow_roots'
    real = (
        "class Guard:\n"
        "    _allowed_roots = ('/a', '/b')\n"
        "    def _decide(self, path):\n"
        "        return path in self._allowed_roots\n"
        "    def allows_write(self, path):\n"
        "        return self._decide(path)\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, real, p.id)
    assert run.did_expand is True, "verifier must bless a guard that delegates to a deciding method"
    assert run.safe is True


def test_attribute_value_constant_is_now_rejected() -> None:
    """A constant returned through a bare class-body ATTRIBUTE VALUE with NO call (``return
    self._ALWAYS``, where ``_ALWAYS = True`` in the class body) is an inert pass-through: always the
    same constant, never inspects its inputs. The resolver now traces a class-body attribute value
    into its constant, so this guard is flagged inert and NOT blessed (the previous residual
    headroom is closed)."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    _ALWAYS = True\n"
        "    def check(self, action):\n"
        "        return self._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "class-body attribute-VALUE constant is inert and must be rejected"
    )


def test_instance_attr_constant_is_now_rejected() -> None:
    """A constant returned through an INSTANCE attribute VALUE bound in ``__init__`` (``return
    self._ALWAYS`` where ``_ALWAYS`` is set in the constructor, not the class body) is an inert
    pass-through: always the same constant, never inspects its inputs. The resolver now traces a
    constructor-bound instance attribute into its constant (and treats a no-return ``__init__`` that
    only assigns constants as inert), so this guard is flagged inert and NOT blessed. This closes the
    previous residual headroom."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def __init__(self):\n"
        "        self._ALWAYS = True\n"
        "    def check(self, action):\n"
        "        return self._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "constructor-bound instance-attribute constant is inert and must be rejected"
    )


def test_method_bound_attr_constant_is_now_rejected() -> None:
    """A constant returned through an INSTANCE attribute bound in a NON-``__init__`` mutator method
    that the guard CALLS (``self._setup()`` then ``return self._ALWAYS``) is an inert pass-through:
    always the same constant, never inspects its inputs, and the binding method is called before the
    read. The resolver now traces a mutator called in the same function that binds the attribute to a
    single provable constant, so this guard is flagged inert and NOT blessed. This closes the previous
    residual headroom."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "    def check(self, action):\n"
        "        self._setup()\n"
        "        return self._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "attribute bound in a called non-__init__ mutator is inert and must be rejected"
    )


def test_factory_indirect_attr_constant_is_now_rejected() -> None:
    """A constant returned through an INSTANCE attribute reached through a factory FUNCTION
    (``_make()._ALWAYS`` where ``_make`` builds a ``_Helper`` whose ``_setup`` bound the attribute) is
    an inert pass-through: the factory returns a fully-inert class instance and the attribute read is
    provably one constant. The resolver now traces a factory's single statically-known return class and
    resolves the attribute constant through the mutator the factory CALLS, so this guard is flagged inert
    and NOT blessed. This closes the previous residual headroom (``factory-hidden``)."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "def _make():\n"
        "    h = SafetyGuard()\n"
        "    h._setup()\n"
        "    return h\n"
        "def check(self, action):\n"
        "    return _make()._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "attribute bound through a factory-function receiver (fully-inert class) is inert and must be rejected"
    )


def test_nested_factory_indirect_attr_constant_is_now_rejected() -> None:
    """The residual headroom ``nested-factory-hidden`` is now CAUGHT: a factory that delegates to
    ANOTHER builder (``_make()`` returns ``_build()``, and the guard reads ``_make()._ALWAYS``) is
    traced to the base builder that directly constructs the class, and the read is resolved to its
    constant — so the guard is flagged inert and NOT blessed."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "def _build():\n"
        "    h = SafetyGuard()\n"
        "    h._setup()\n"
        "    return h\n"
        "def _make():\n"
        "    return _build()\n"
        "def check(self, action):\n"
        "    return _make()._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "attribute bound through a factory that delegates to another builder (traced to the base "
        "constructor) is an inert pass-through and must now be rejected"
    )


def test_static_factory_indirect_attr_constant_is_now_rejected() -> None:
    """A constant returned through an INSTANCE attribute reached through a FACTORY METHOD
    (``SafetyGuard.create()._ALWAYS``, where ``create`` is a ``@staticmethod`` that builds and returns a
    fully-inert ``SafetyGuard``) is an inert pass-through: always the same constant, never inspects its
    inputs. The resolver now traces a class-level factory METHOD's single statically-known return class
    (following a method→method delegation chain) and resolves the attribute constant through the mutator
    the method CALLS, so this guard is flagged inert and NOT blessed. Closes the ``static-factory-hidden``
    residual headroom."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "    @staticmethod\n"
        "    def create():\n"
        "        h = SafetyGuard()\n"
        "        h._setup()\n"
        "        return h\n"
        "    def check(self, action):\n"
        "        return SafetyGuard.create()._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "attribute bound through a class-level factory-method receiver (fully-inert class) is an inert "
        "pass-through and must now be rejected"
    )
    assert run.safe is True


def test_nested_static_factory_indirect_attr_constant_is_now_rejected() -> None:
    """A constant reached through a factory method that DELEGATES to ANOTHER factory method on the same
    class (``SafetyGuard.create()`` returns ``_build()``, and the guard reads ``SafetyGuard.create()._ALWAYS``)
    is now REJECTED: the resolver follows a method→method delegation chain to the base builder that directly
    constructs the class, then resolves the attribute constant through the mutator the base builder CALLS, so
    the guard is flagged inert and NOT blessed. It carries the pattern, valid Python."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "    @staticmethod\n"
        "    def _build():\n"
        "        h = SafetyGuard()\n"
        "        h._setup()\n"
        "        return h\n"
        "    @staticmethod\n"
        "    def create():\n"
        "        return _build()\n"
        "    def check(self, action):\n"
        "        return SafetyGuard.create()._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "a constant reached through a factory method that delegates to another factory method must now be "
        "rejected (the resolver traces the method→method factory delegation chain to the base builder)"
    )
    assert run.safe is True


def test_classmethod_cls_factory_is_now_rejected_and_nested_is_headroom() -> None:
    """A constant reached through a CLASSMETHOD factory that builds via the ``cls`` receiver
    (``SafetyGuard.create()`` does ``h = cls(); h._setup(); return h``, the guard reads
    ``SafetyGuard.create()._ALWAYS``) is NOW CAUGHT: the resolver traces a classmethod factory's ``cls()``
    construction back to the receiver class (the ``cls`` first-arg of a ``@classmethod`` IS the class it is
    called on), so the inert pass-through no longer blesses. This fire the resolver also threads the ``cls``
    receiver through a classmethod→classmethod DELEGATION chain to the base builder, so a classmethod factory
    that DELEGATES to a SIBLING classmethod (``create()`` returns ``_build()``, both ``@classmethod``) is now
    caught too. The honest residual headroom moved one ratchet step deeper to a classmethod factory CALLED ON
    AN INSTANCE RECEIVER (``SafetyGuard().create()``) — a ``_Cls(...)`` construction, not a bare class name,
    which the receiver-class resolver cannot tie to a class, so the read stays non-constant and the guard still
    blesses. Carries the pattern, valid Python."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    direct = (
        "class SafetyGuard:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        h = cls()\n"
        "        h._setup()\n"
        "        return h\n"
        "    def check(self, action):\n"
        "        return SafetyGuard.create()._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, direct, p.id)
    assert run.did_expand is False, (
        "a constant reached through a @classmethod factory that builds via the cls receiver must now be "
        "rejected (the resolver traces the cls() construction back to the receiver class)"
    )
    assert run.safe is True
    nested = (
        "class SafetyGuard:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "    @classmethod\n"
        "    def _build(cls):\n"
        "        h = cls()\n"
        "        h._setup()\n"
        "        return h\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        return _build()\n"
        "    def check(self, action):\n"
        "        return SafetyGuard.create()._ALWAYS\n"
    )
    run_nested = TraceabilityVerifier.classify(p.pattern, p.violations, nested, p.id)
    assert run_nested.did_expand is False, (
        "a constant reached through a classmethod factory that delegates to a sibling classmethod must now "
        "be rejected (the resolver threads the cls() receiver through the classmethod delegation chain)"
    )
    assert run_nested.safe is True
    instance = (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        h = cls()\n"
        "        h._setup()\n"
        "        return h\n"
        "class SafetyGuard:\n"
        "    def check(self, action):\n"
        "        return _Helper().create()._ALWAYS\n"
    )
    run_instance = TraceabilityVerifier.classify(p.pattern, p.violations, instance, p.id)
    assert run_instance.did_expand is True, (
        "a constant reached through a classmethod factory called on an INSTANCE receiver (_Helper().create()) "
        "is the new honest residual headroom (the receiver is a _Cls(...) construction the resolver cannot "
        "tie to a class) and must still bless"
    )
    assert run_instance.safe is True


def test_classmethod_factory_returning_cls_directly_is_rejected() -> None:
    """A classmethod factory that returns a DIRECT ``cls()`` construction (``return cls()`` with no local
    assignment) is an inert pass-through when the built class's attribute is a provable constant: the
    resolver resolves a bare ``cls()`` call back to the receiver class, so the constant read is caught. This
    covers the direct-construction edge (a real ``return cls()`` classmethod factory) which the
    ``h = cls(); return h`` shape does not exercise."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    _ALWAYS = True\n"
        "    @classmethod\n"
        "    def create(cls):\n"
        "        return cls()\n"
        "    def check(self, action):\n"
        "        return SafetyGuard.create()._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "a constant reached through a @classmethod factory that returns a DIRECT cls() construction must "
        "be rejected (the resolver resolves a bare cls() call to the receiver class)"
    )
    assert run.safe is True


def test_static_factory_that_decides_on_state_is_still_blessed() -> None:
    """Anti-over-rejection: a real guard that reads an attribute off a static-factory-returned instance
    where the built guard genuinely DECIDES on state (``check`` returns ``path in roots``, a non-constant)
    is a real decision, not a pass-through. The resolver refuses to prove a constant (the class is not
    fully-inert, and the attribute is never bound to a single constant), so the guard stays blessed."""
    p = _constitution().principles[0]  # SEC-01 'allows_write|_is_within|allow_roots'
    guard = (
        "class _Guard:\n"
        "    _allowed_roots = ('/a', '/b')\n"
        "    def allows_write(self, path):\n"
        "        return path in self._allowed_roots\n"
        "    @staticmethod\n"
        "    def create():\n"
        "        return _Guard()\n"
        "def allows_write(self, path):\n"
        "    return _Guard.create().allows_write(path)\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, (
        "a static-factory-returned instance that genuinely decides on state must stay a real guard"
    )
    assert run.safe is True


def test_factory_that_decides_on_state_is_still_blessed() -> None:
    """Anti-over-rejection: a real guard that reads an attribute off a factory-returned instance where
    the factory builds a REAL, state-deciding guard (``check`` returns ``path in roots``, a non-constant)
    is a genuine decision, not an inert pass-through. The resolver refuses to prove a constant (the class
    is not fully-inert), so the guard stays blessed."""
    p = _constitution().principles[0]  # SEC-01 'allows_write|_is_within|allow_roots'
    guard = (
        "class _Guard:\n"
        "    _allowed_roots = ('/a', '/b')\n"
        "    def allows_write(self, path):\n"
        "        return path in self._allowed_roots\n"
        "def _make():\n"
        "    return _Guard()\n"
        "def allows_write(self, path):\n"
        "    return _make().allows_write(path)\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, (
        "a factory-returned instance that genuinely decides on state must stay a real guard"
    )
    assert run.safe is True


def test_dynamic_factory_return_is_still_blessed() -> None:
    """Anti-over-rejection: a factory whose return type is genuinely dynamic — it returns a parameter
    or an expression the resolver cannot tie to a statically-known class — is NOT resolved, so an
    attribute read off it stays non-constant and the guard is blessed (the resolver only proves a
    constant for a factory that provably returns ONE fully-inert class built directly)."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def _setup(self):\n"
        "        self._ALWAYS = True\n"
        "def _make(kind):\n"
        "    if kind == 'a':\n"
        "        return SafetyGuard()\n"
        "    return None\n"
        "def check(self, action):\n"
        "    return _make('a')._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, (
        "a factory with a dynamic/branching return type is not a provable single-constant receiver"
    )


def test_nested_factory_that_decides_on_state_is_still_blessed() -> None:
    """Anti-over-rejection for the factory-CHAIN recursion: a guard that reads through a nested factory
    (``_make()`` -> ``_build()``) which builds a REAL state-deciding guard (``allows_write`` returns
    ``path in roots``, a non-constant) is a genuine decision, not an inert pass-through. The resolver
    refuses to prove a constant (the built class is not fully-inert), so the guard stays blessed."""
    p = _constitution().principles[0]  # SEC-01 'allows_write|_is_within|allow_roots'
    guard = (
        "class _Guard:\n"
        "    _allowed_roots = ('/a', '/b')\n"
        "    def allows_write(self, path):\n"
        "        return path in self._allowed_roots\n"
        "def _build():\n"
        "    return _Guard()\n"
        "def _make():\n"
        "    return _build()\n"
        "def allows_write(self, path):\n"
        "    return _make().allows_write(path)\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, (
        "a nested-factory-returned instance that genuinely decides on state must stay a real guard"
    )
    assert run.safe is True


def test_nested_factory_receiver_attr_not_provable_is_blessed() -> None:
    """Anti-over-rejection for the factory-CHAIN recursion: a guard that reads an attribute off a nested
    factory receiver (``_make()._ALWAYS``) where the attribute is NEVER bound to a provable constant is
    a real decision, not an inert pass-through. The resolver refuses to prove a constant (no class-body /
    ``__init__`` / called-mutator binding of ``_ALWAYS``), so the guard stays blessed."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def __init__(self):\n"
        "        self._enabled = True\n"
        "def _build():\n"
        "    return SafetyGuard()\n"
        "def _make():\n"
        "    return _build()\n"
        "def check(self, action):\n"
        "    return _make()._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, (
        "an attribute read off a nested factory receiver that is never bound to a provable constant "
        "must stay a real decision"
    )
    assert run.safe is True


def test_real_guard_method_only_is_still_blessed() -> None:
    """Anti-over-rejection guard for the factory receiver change: a real ``check`` that decides on its
    inputs (returns ``action in self._allowed``, a Compare) is NOT inert; the presence of a factory
    function in the module must not flip a genuinely deciding guard into a rejected inert shell."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    _allowed = ('read', 'write')\n"
        "    def check(self, action):\n"
        "        return action in self._allowed\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, "a real branching guard must stay blessed"


def test_constructor_bound_attr_from_argument_is_real_guard() -> None:
    """Anti-over-rejection: a constructor that sets ``self._allowed = allowed`` from an ARGUMENT (a
    non-constant) and ``check`` returns it is NOT an inert pass-through — the value is per-instance, so
    the resolver must refuse to prove a single constant (``_resolve_literal_key`` on a non-constant Name
    fails) and the guard stays blessed. This is the key false-negative guard for the constructor-bound
    instance-attribute resolution."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def __init__(self, allowed):\n"
        "        self._allowed = allowed\n"
        "    def check(self, action):\n"
        "        return self._allowed\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, (
        "a constructor bound from an argument is a real decision and must stay blessed"
    )


def test_constructor_reassigned_attr_is_not_a_constant() -> None:
    """Anti-over-rejection: if ``__init__`` assigns ``self._ALWAYS`` TWICE (True then False), the
    resolver must NOT claim a single constant (a reassignment is a real decision, not a fixed value), so
    the guard stays blessed. Without this ``found is not None`` guard, a real guard that mutates state
    would be misjudged inert."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def __init__(self):\n"
        "        self._ALWAYS = True\n"
        "        self._ALWAYS = False\n"
        "    def check(self, action):\n"
        "        return self._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, (
        "a reassigned constructor attribute is a real decision and must stay blessed"
    )


def test_constructor_sets_other_attribute_still_headroom() -> None:
    """The resolver only follows the asked-for attribute: a constructor that sets ``self._other`` (not
    ``self._ALWAYS``) provides no constant for the guard's ``return self._ALWAYS``, so the guard stays
    blessed (it reads an attribute that is never provably constant). Exercises the non-matching /
    no-assignment defensive paths."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def __init__(self):\n"
        "        self._other = True\n"
        "    def check(self, action):\n"
        "        return self._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is True, (
        "an attribute that is never bound to a provable constant must stay a real decision"
    )


def test_constructor_with_extra_statement_still_inert() -> None:
    """A constructor that has an inert non-``Assign`` statement (a ``pass``) before the constant set
    still binds ``self._ALWAYS`` to a single constant, so the guard remains an inert pass-through and
    is rejected. Exercises the non-``Assign``-statement skip (a ``pass``) in the constructor scan — the
    same skip that a real setup CALL would also hit, but a call makes the class non-inert (a real
    action), whereas a ``pass`` does not."""
    p = _constitution().principles[1]  # SEC-02 'class SafetyGuard|_HIGH_RISK_ACTIONS'
    guard = (
        "class SafetyGuard:\n"
        "    def __init__(self):\n"
        "        pass\n"
        "        self._ALWAYS = True\n"
        "    def check(self, action):\n"
        "        return self._ALWAYS\n"
    )
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "a constructor-bound constant with an extra inert statement is still inert"
    )


def test_module_class_attribute_value_is_rejected() -> None:
    """A constant returned through a bare attribute VALUE referencing a MODULE-LEVEL CLASS by name
    (``return _Mod.val`` where ``_Mod`` is a class with ``val = True`` in its body) is the same inert
    pass-through read through the class object rather than an instance. The resolver traces a class
    referenced by bare name too, so this guard is flagged inert and NOT blessed."""
    p = _constitution().principles[2]  # SEC-03 'def redact_value|_redact_text|redact_secrets'
    guard = "class _Mod:\n    val = True\ndef redact_value(text):\n    return _Mod.val\n"
    run = TraceabilityVerifier.classify(p.pattern, p.violations, guard, p.id)
    assert run.did_expand is False, (
        "module-class attribute VALUE constant must be rejected as inert"
    )
