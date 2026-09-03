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
"""

from __future__ import annotations

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


def mutant_cases(principle: Principle) -> list[MutantCase]:
    """The defect guards a cheater ships for a principle, with trustworthy verdicts."""
    tok = _first_token(principle.pattern)
    return [
        # A dead stub: the class name is present but there is no logic behind it.
        MutantCase("stub", f"class {tok}:\n    pass\n", False),
        # The pattern token appears only inside a comment — no real implementation.
        MutantCase("comment", f"# {tok}\n", False),
        # The guard is entirely absent — nothing was implemented.
        MutantCase("absent", "", False),
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
