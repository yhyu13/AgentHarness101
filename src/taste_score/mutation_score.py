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
shell) but still can't tell a *partial* guard — one that carries the symbol and real code yet
does nothing effective — from a real one. Each missed fake is honest headroom; hardening the
verifier raises the score, and you can always add a subtler mutant, so it never truly
saturates.

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
