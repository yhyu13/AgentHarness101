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
        nothing rather than everything. Includes both correct (repeat) and avoid lessons.
        """
        return self._lessons(objective, correct=None, limit=limit)

    def repeat_lessons(self, objective: str, limit: int = 5) -> list[MemoryFact]:
        """Lessons worth repeating (``correct=True``): what worked, keep doing it."""
        return self._lessons(objective, correct=True, limit=limit)

    def avoid_lessons(self, objective: str, limit: int = 5) -> list[MemoryFact]:
        """Lessons to avoid (``correct=False``): the standing Do-Not-Repeat list.

        These are surfaced explicitly rather than filtered out, so a past mistake is
        injected into the next run's steering instead of being invisible to it (D3).
        """
        return self._lessons(objective, correct=False, limit=limit)

    def _lessons(self, objective: str, correct: bool | None, limit: int) -> list[MemoryFact]:
        tokens = _tokens(objective)
        if not tokens:
            return []
        matches = [
            fact
            for fact in self._hippocampus.facts()
            if fact.key.startswith("self-improve::")
            and (correct is None or fact.correct is correct)
            and (tokens & _tokens(fact.value))
        ]
        return matches[:limit]

    def steering_context(self, objective: str, limit: int = 5) -> str:
        """Render relevant lessons as a block to prepend to the anti-drift steering.

        Repeat lessons appear under "Prior lessons"; avoid lessons are injected as a
        standing "Do not repeat" instruction so past mistakes are never invisible.
        """
        repeats = self.repeat_lessons(objective, limit=limit)
        avoids = self.avoid_lessons(objective, limit=limit)
        if not repeats and not avoids:
            return ""
        lines = ["## Prior lessons on similar goals"]
        lines.extend(f"- {lesson.value}" for lesson in repeats)
        if avoids:
            lines.extend(["", "## Do not repeat", ""])
            lines.extend(f"- {lesson.value}" for lesson in avoids)
        return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))
