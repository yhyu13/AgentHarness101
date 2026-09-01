from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
import re
from typing import Iterable

from context_compaction.models import ContextItem


class Summarizer(ABC):
    """Condenses a batch of archived items into a single context string.

    This is the only extension point where an LLM-backed summarizer can be swapped in.
    The default is a deterministic extractive fallback so the harness works without a
    model, matching the rest of this repo's no-LLM testing discipline.
    """

    @abstractmethod
    def summarize(self, items: Iterable[ContextItem]) -> str: ...


class ExtractiveSummarizer(Summarizer):
    """Deterministic keyword-led summary for testing and offline use.

    It reports the item count, the dominant terms, and a truncated first line from each
    item. It is deliberately lossy and mechanical — good enough to prove the pipeline,
    not a substitute for a real model summarizer in production.
    """

    def __init__(self, max_items: int = 3, max_chars: int = 800) -> None:
        self._max_items = max_items
        self._max_chars = max_chars

    def summarize(self, items: Iterable[ContextItem]) -> str:
        material = list(items)
        if not material:
            return ""

        words = [
            w
            for item in material
            for w in re.findall(r"[A-Za-z\u4e00-\u9fff_]{2,}", item.content.lower())
        ]
        top = [w for w, _ in Counter(words).most_common(5)]
        terms = ", ".join(top) if top else "(no keywords)"

        lines = []
        for item in material[: self._max_items]:
            first = item.content.strip().splitlines()[0] if item.content.strip() else ""
            if len(first) > 120:
                first = first[:120] + "…"
            lines.append(f"- [{item.source or item.id}] {first}")

        body = "\n".join(lines) if lines else "(no excerpt)"
        summary = f"Archived {len(material)} item(s). Keywords: {terms}.\n{body}"
        return summary[: self._max_chars]
