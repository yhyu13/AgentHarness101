"""Verifier mutation-score — the non-saturable dimension (quality-benchmark-design).

``csdd_score`` saturates at 1.0 once every constitution principle is implemented+clean.
That saturation is a defect in the MEASURE, not a sign the thing is perfect: the engine's
own anti-Goodhart claim ("the gate catches a cheater") is unmeasured. The honest,
non-saturable measure is the VERIFIER's own strength — inject the kinds of guards a
cheating agent would actually ship (a dead stub, a pattern token that appears only in a
comment, an entirely absent guard) and count what fraction the verifier REFUSES to bless
as a genuine safe expansion.

A defect is ``blessed`` (the verifier fails) when ``classify`` returns
``did_expand=True and safe=True`` for something that is NOT a real capability. The verifier
refuses to bless a bare placeholder (a dead ``class X: pass``, a comment-only/docstring-only
shell), and hardened past that it now also refuses to bless an *inert pass-through* — a guard
that carries the symbol AND real code yet always returns the same constant without inspecting
its inputs (``def allows_write(...): return True``, the 'always allow' cheat). Hardening gets
progressively subtler: a constant returned through a NAME (``return ALWAYS``), a top-level helper call
(``return _always()``), an attribute/method call (``return self._always()``), then a bare attribute
value (``return self._ALWAYS``) — each is caught when caught, and each reveals a subtler still-unsolved
one, so the measure never truly saturates.

The inert-guard hardening has already caught the literal-return (``partial``) pass-through, the
Name-returned (``constant-hidden``) one, the top-level HELPER-CALL (``helper-hidden``) one
(``return _always(...)``), the ATTRIBUTE/METHOD-CALL (``attribute-hidden``) one
(``return self._always(...)`` / ``return _Helper().always(...)``), the bare ATTRIBUTE VALUE
(``attr-value-hidden``) one (``return self._ALWAYS`` where ``_ALWAYS = True`` in the class body),
and — this fire — the CONSTRUCTOR-BOUND INSTANCE ATTRIBUTE (``instance-attr-hidden``) one
(``return self._ALWAYS`` where ``_ALWAYS = True`` in ``def __init__``), which the resolver now traces
into the constructor assignment. The current residual headroom is ``inst-attr-mutator-hidden``: a
constant returned through an INSTANCE attribute bound in a NON-``__init__`` mutator method
(``self._ALWAYS = True`` inside ``_setup()``, read in ``check()``) that the resolver only proves for a
NAME / a top-level helper CALL / a bound-method CALL / a class-body attribute VALUE / an
``__init__``-bound instance attribute, so it still blesses. Each ratchet step is: catch this level,
add a subtler one.

The fake generator must emit ONLY valid Python: a fake like ``class class Guard: pass`` is a
MEASUREMENT BUG, because the verifier's parse-error fallback then blesses an impossible fake
and the score is deflated for the wrong reason. Every fake models something a cheater could
realistically ship — a dead class, a nested shell, or an inert-but-real guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from taste_score.constitution import Constitution, Principle
from taste_score.trace import TraceabilityVerifier


@dataclass(frozen=True, slots=True)
class MutantCase:
    """One injected guard-fake and the verdict a trustworthy verifier should reach."""

    label: str
    text: str
    expected_genuine: bool  # True only for a REAL implemented guard; fakes are False.


def _first_token(pattern: str) -> str:
    """The first alternative of a ``pattern`` (e.g. 'a|b|c' -> 'a')."""
    return pattern.split("|")[0].strip()


def _callable_name(token: str) -> str | None:
    """A class/def name drawn from a ``class X`` / ``def y`` / ``async def y`` token."""
    m = re.match(r"\b(?:async\s+)?(?:class|def)\s+([A-Za-z_]\w*)", token)
    return m.group(1) if m else None


def _guard_symbol(token: str) -> str | None:
    """A name safe to drop into a class/def header; None for a statement-fragment token."""
    name = _callable_name(token)
    if name:
        return name
    if re.fullmatch(r"[A-Za-z_]\w*", token):
        return token
    return None


def _stub(token: str) -> str:
    """A dead shell: the guard's name is present but there is no logic behind it."""
    sym = _guard_symbol(token)
    if sym:
        return f"class {sym}:\n    pass\n"
    # A statement-fragment token (e.g. 'permission not in self\\._enabled') has no nameable
    # symbol; the honest dead shell is a guard function with an empty body.
    return "def _guard():\n    pass\n"


def _nested(token: str) -> str:
    """A dead shell hidden inside an unused wrapper — a top-level-only placeholder check
    blesses it; a recursive one must not."""
    sym = _guard_symbol(token)
    if sym:
        return f"def _unused():\n    class {sym}:\n        pass\n"
    return "def _unused():\n    def _guard():\n        pass\n"


def _partial(token: str) -> str:
    """A guard carrying the symbol AND real code yet doing nothing effective — the honest
    semantic ceiling this verifier can only catch by semantics, not by regex/dead-stub."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return f"def _guard():\n    if {literal}:\n        pass\n    return True\n"
    if _callable_name(token):
        if token.strip().startswith("class"):
            return f"class {sym}:\n    def check(self, action):\n        return True\n"
        return f"def {sym}(*args, **kwargs):\n    return None\n"
    return f"{sym} = ()\n"


def _call_constant_hidden(token: str) -> str:
    """A guard returning its constant through a *helper call* (``return _always(...)``).

    The constant-return detector resolves a returned NAME (``return ALWAYS``) but (before the
    helper-call hardening) could not trace a CALL into a helper that itself returns a constant. So
    a cheater ships ``_always() -> True`` and a guard that delegates to it: the guard carries the
    symbol AND real code, inspects nothing, always returns True, yet the verifier blesses it. This
    is the now-CAUGHT ratchet step once ``constant-hidden`` (Name-returned) is caught — the resolver
    traces a top-level helper call to its constant. Carries the pattern, valid Python.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "def _always():\n"
            "    return True\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _always()\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return (
                "def _always(self, action):\n"
                "    return True\n"
                f"class {sym}:\n"
                "    def check(self, action):\n"
                "        return _always(self, action)\n"
            )
        return (
            "def _always(*args, **kwargs):\n"
            "    return True\n"
            f"def {sym}(*args, **kwargs):\n"
            "    return _always(*args, **kwargs)\n"
        )
    return f"def _always():\n    return True\n{sym} = _always()\n"


def _attribute_hidden(token: str) -> str:
    """A guard returning its constant through an *attribute/method call* (``return self._always()``).

    Once the resolver traces a top-level bare-name HELPER CALL, the next honest headroom is a
    helper reached through an ATTRIBUTE (a method on ``self``/an instance, ``_Helper().always()``).
    The detector only proves a constant for a plain-``Name`` call to a module-level function, so a
    constant delegated through ``self._always()``/``_Helper().always()`` STILL blesses — this is the
    'add a subtler mutant' ratchet once ``helper-hidden`` is caught. Carries the pattern, valid Python.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def always(self):\n"
            "        return True\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper().always()\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return (
                f"class {sym}:\n"
                "    def _always(self, action):\n"
                "        return True\n"
                "    def check(self, action):\n"
                "        return self._always(action)\n"
            )
        return (
            "class _Helper:\n"
            "    def always(self, *args, **kwargs):\n"
            "        return True\n"
            f"def {sym}(*args, **kwargs):\n"
            "    return _Helper().always(*args, **kwargs)\n"
        )
    return (
        f"class _Helper:\n    def always(self):\n        return True\n{sym} = _Helper().always()\n"
    )


def _attr_value_hidden(token: str) -> str:
    """A guard returning its constant through a bare ATTRIBUTE VALUE with NO call (``return
    self._ALWAYS``, where ``_ALWAYS`` is a class attribute).

    Once the resolver traces a BOUND-METHOD CALL (``self._always()``), the next honest headroom is a
    constant returned through a plain attribute VALUE rather than a call — the resolver proves a
    constant for a NAME, a top-level helper CALL, and a bound-method CALL, but an ``ast.Attribute``
    VALUE falls through to non-constant, so this guard STILL blesses. Carries the pattern, valid
    Python — the 'add a subtler mutant' ratchet once ``attribute-hidden`` is caught.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    val = True\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper().val\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return (
                f"class {sym}:\n"
                "    _ALWAYS = True\n"
                "    def check(self, action):\n"
                "        return self._ALWAYS\n"
            )
        return (
            "class _Helper:\n"
            "    val = True\n"
            f"def {sym}(*args, **kwargs):\n"
            "    return _Helper().val\n"
        )
    return f"class _Helper:\n    val = True\n{sym} = _Helper().val\n"


def _instance_attr_hidden(token: str) -> str:
    """A guard returning its constant through an INSTANCE attribute set in ``__init__`` (``return
    self._ALWAYS`` where ``_ALWAYS`` is bound in ``def __init__``, not in the class body).

    Once the resolver traces a bare class-body attribute VALUE (``self._ALWAYS`` with ``_ALWAYS =
    True`` in the class body), the next honest headroom was an attribute bound to its constant in the
    CONSTRUCTOR — the resolver then only looked at class-body assignments, so an instance attribute set
    at build time still read as a real decision and blessed. This is the now-CAUGHT level: the resolver
    traces a constructor-bound instance attribute (and treats a no-return ``__init__`` that only assigns
    constants as inert), so this fake is rejected. Carries the pattern, valid Python — the 'add a
    subtler mutant' ratchet that ``inst-attr-mutator-hidden`` now supersedes.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def __init__(self):\n"
            "        self.val = True\n"
            "def _guard():\n"
            "    if " + literal + ":\n"
            "        return True\n"
            "    return _Helper().val\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return (
                f"class {sym}:\n"
                "    def __init__(self):\n"
                "        self._ALWAYS = True\n"
                "    def check(self, action):\n"
                "        return self._ALWAYS\n"
            )
        return (
            "class _Helper:\n"
            "    def __init__(self):\n"
            "        self.val = True\n"
            f"def {sym}(*args, **kwargs):\n"
            "    return _Helper().val\n"
        )
    return (
        f"class _Helper:\n    def __init__(self):\n        self.val = True\n{sym} = _Helper().val\n"
    )


def _method_bound_attr_hidden(token: str) -> str:
    """A guard returning its constant through an INSTANCE attribute bound in a NON-``__init__``
    mutator method (``return self._ALWAYS`` where ``self._ALWAYS = True`` is set inside ``_setup()``,
    not the class body or constructor).

    Once the resolver traces an ``__init__``-bound instance attribute, the next honest headroom is an
    attribute bound in an ARBITRARY method — the resolver only looks at class-body assignments and the
    constructor, so an instance attribute set at ``_setup()`` then read by ``check()`` still reads as a
    real decision and blesses. Carries the pattern, valid Python — the 'add a subtler mutant' ratchet
    once ``instance-attr-hidden`` is caught.
    """
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            "class _Helper:\n"
            "    def _setup(self):\n"
            "        self.val = True\n"
            "    def check(self):\n"
            "        if " + literal + ":\n"
            "            return True\n"
            "        self._setup()\n"
            "        return self.val\n"
        )
    if token.strip().startswith("class"):
        return (
            f"class {sym}:\n"
            "    def _setup(self):\n"
            "        self._ALWAYS = True\n"
            "    def check(self, action):\n"
            "        self._setup()\n"
            "        return self._ALWAYS\n"
        )
    # A def-name OR a bare-identifier symbol: a function that reads an instance attribute bound in a
    # non-__init__ mutator. `<sym>` returns `h.val` (never proven constant — bound in `_setup`, not the
    # constructor), so it stays a real decision and the module is NOT inert -> still blessed.
    return (
        "class _Helper:\n"
        "    def _setup(self):\n"
        "        self.val = True\n"
        f"def {sym}(*args, **kwargs):\n"
        "    h = _Helper()\n"
        "    h._setup()\n"
        "    return h.val\n"
    )


def _constant_hidden(token: str) -> str:
    """A guard that returns a value through a *name* (``return ALWAYS``), not a literal — so the
    return LOOKS like it could depend on state but is really a fixed module constant. The
    constant-return detector cannot trace it (the return node is a ``Name``, not a literal), so
    this is a subtler pass-through that still blesses. Carries the symbol AND real code, decides
    nothing — the 'add a subtler mutant' ratchet once the inert pass-through is caught."""
    sym = _guard_symbol(token)
    if not sym:
        literal = token.replace("\\", "")
        return (
            f"ALWAYS = True\n"
            f"def _guard():\n"
            f"    if {literal}:\n"
            f"        return True\n"
            f"    return ALWAYS\n"
        )
    if _callable_name(token):
        if token.strip().startswith("class"):
            return f"ALWAYS = True\nclass {sym}:\n    def check(self, action):\n        return ALWAYS\n"
        return f"ALWAYS = True\ndef {sym}(*args, **kwargs):\n    return ALWAYS\n"
    return f"ALWAYS = True\n{sym} = ALWAYS\n"


def mutant_cases(principle: Principle) -> list[MutantCase]:
    """The defect guards a cheater ships for a principle, with trustworthy verdicts."""
    tok = _first_token(principle.pattern)
    return [
        # A dead stub: the class name is present but there is no logic behind it.
        MutantCase("stub", _stub(tok), False),
        # The pattern token appears only inside a comment — no real implementation.
        MutantCase("comment", f"# {tok}\n", False),
        # The guard is entirely absent — nothing was implemented.
        MutantCase("absent", "", False),
        # A dead shell nested inside an unused wrapper (harder for a top-level check).
        MutantCase("nested", _nested(tok), False),
        # A guard that carries the symbol and real code yet does nothing effective.
        MutantCase("partial", _partial(tok), False),
        # A pass-through whose returned constant is hidden behind a NAME — subtler still.
        MutantCase("constant-hidden", _constant_hidden(tok), False),
        # A pass-through whose constant is returned through a HELPER CALL — subtler than both.
        MutantCase("helper-hidden", _call_constant_hidden(tok), False),
        # A pass-through whose constant is returned through an ATTRIBUTE/METHOD call — subtler still
        # (now CAUGHT: the resolver traces a bound-method call to its constant).
        MutantCase("attribute-hidden", _attribute_hidden(tok), False),
        # A pass-through whose constant is returned through a bare ATTRIBUTE VALUE (no call) — now
        # CAUGHT: the resolver traces a class-body attribute value (self._ALWAYS with _ALWAYS = True)
        # to its constant.
        MutantCase("attr-value-hidden", _attr_value_hidden(tok), False),
        # A pass-through whose constant is returned through an INSTANCE attribute set in __init__
        # (return self._ALWAYS where _ALWAYS is bound in the constructor, not the class body) — now
        # CAUGHT: the resolver traces a constructor-bound instance attribute into its constant.
        MutantCase("instance-attr-hidden", _instance_attr_hidden(tok), False),
        # A pass-through whose constant is returned through an INSTANCE attribute bound in a NON-
        # __init__ mutator method (self._ALWAYS set in _setup(), read in check()) — the honest
        # residual headroom once an __init__-bound attribute is traced (the resolver proves a constant
        # for a NAME / top-level helper CALL / bound-method CALL / class-body attribute VALUE /
        # __init__-bound instance attribute, not one bound in an arbitrary method).
        MutantCase("inst-attr-mutator-hidden", _method_bound_attr_hidden(tok), False),
    ]


def verifier_strength(constitution: Constitution) -> float:
    """Fraction of injected guard-fakes the verifier refuses to bless.

    = 1.0 would mean the verifier rejects every fake (perfect for the current mutant set).
    < 1.0 is honest, non-saturable headroom: return value is ``(total - blessed) / total``.
    """
    total = 0
    blessed = 0
    for p in constitution.principles:
        for case in mutant_cases(p):
            total += 1
            run = TraceabilityVerifier.classify(p.pattern, p.violations, case.text, p.id)
            if run.did_expand and run.safe:
                blessed += 1  # the regex "blessed" a fake guard as a genuine safe expansion
    return 0.0 if total == 0 else (total - blessed) / total
