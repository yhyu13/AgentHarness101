from __future__ import annotations

import re
from typing import Optional

from hippocampus import Hippocampus
from hippocampus.models import MemoryFact


_WORD_RE = re.compile(r"[A-Za-z0-9_]{3,}")


class SelfImprover:
    """Close the "越跑越好" loop: distill a finished run into a durable lesson and
    re-inject relevant lessons into the next run's steering.

    The hippocampus already records trajectories and facts; this module makes that
    memory *self-improving* (harness-skills survey §5: claude-mem
    ``capture→compress→reinject``, self-rag self-reflection, Acontext "skills as
    memory"). Distillation and retrieval are deterministic pure functions over the
    hippocampus index — no LLM call, so the "only mock the LLM boundary" rule is
    untouched.
    """

    def __init__(self, hippocampus: Hippocampus) -> None:
        self._hippocampus = hippocampus

    # ------------------------------------------------------------------ distill

    def distill(
        self,
        thread_id: str,
        objective: str,
        status: str,
        summary: str,
        issues: Optional[list[str]] = None,
    ) -> MemoryFact:
        """Turn one finished run into a durable lesson.

        A completed run is a *repeat* lesson (``correct=True`` — keep doing this); any
        other terminal (blocked, budget-limited, stopped) is an *avoid* lesson
        (``correct=False`` — stop repeating this). The objective is folded into the
        value so relevance matching has something to key on.
        """
        repeatable = status == "complete"
        label = "repeat" if repeatable else "avoid"
        value = f"[{label}] {objective} — {summary}"
        if issues:
            value += " (issues: " + "; ".join(issues) + ")"
        fact = MemoryFact(
            key=f"self-improve::{thread_id}",
            value=value,
            correct=repeatable,
            evidence=summary,
            source="self-improve",
        )
        self._hippocampus.learn(fact.key, fact.value, correct=fact.correct, evidence=fact.evidence)
        return fact

    # ------------------------------------------------------------------ retrieve

    def relevant_lessons(self, objective: str, limit: int = 5) -> list[MemoryFact]:
        """Return lessons whose value shares a content word with ``objective``.

        Relevance is token overlap (words of length >= 3), so it is deterministic and
        cheap enough to run every round. Empty objective (no content words) matches
        nothing rather than everything.
        """
        tokens = _tokens(objective)
        if not tokens:
            return []
        matches = [
            fact
            for fact in self._hippocampus.facts()
            if fact.key.startswith("self-improve::") and (tokens & _tokens(fact.value))
        ]
        return matches[:limit]

    def steering_context(self, objective: str, limit: int = 5) -> str:
        """Render relevant lessons as a block to prepend to the anti-drift steering."""
        lessons = self.relevant_lessons(objective, limit=limit)
        if not lessons:
            return ""
        lines = [f"- {lesson.value}" for lesson in lessons]
        return "## Prior lessons on similar goals\n" + "\n".join(lines)


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))
