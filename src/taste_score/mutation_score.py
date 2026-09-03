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
its inputs (``def allows_write(...): return True``, the 'always allow' cheat). It still can't
It still can't tell a *partial/constant-hidden* guard — one whose constant is returned through a
NAME (``return ALWAYS``) so the decision LOOKS state-dependent but is really fixed — from a real one.
Each missed fake is honest headroom; hardening the verifier raises the score, and you can
always add a subtler mutant, so it never truly saturates.

The inert-guard hardening has already caught the literal-return (``partial``) pass-through, the
Name-returned (``constant-hidden``) one, the top-level HELPER-CALL (``helper-hidden``) one
(``return _always(...)``), and — this fire — the ATTRIBUTE/METHOD-CALL (``attribute-hidden``) one
(``return self._always(...)`` / ``return _Helper().always(...)``), which the resolver now traces into
the bound method. The current residual headroom is ``attr-value-hidden``: a constant returned through
a bare attribute VALUE with no call (``return self._ALWAYS``) that the resolver only proves for a
NAME / a top-level helper CALL / a bound-method CALL, so it still blesses. Each ratchet step is: catch
this level, add a subtler one.

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
        # A pass-through whose constant is returned through a bare ATTRIBUTE VALUE (no call) — the
        # honest residual headroom once a bound-method CALL is traced (the resolver proves a
        # constant for a NAME / top-level helper CALL / bound-method CALL, not an Attribute value).
        MutantCase("attr-value-hidden", _attr_value_hidden(tok), False),
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
