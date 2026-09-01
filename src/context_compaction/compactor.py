from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

from context_compaction.models import CompactionResult, ContextItem
from context_compaction.summarizer import ExtractiveSummarizer, Summarizer


class ContextCompactor:
    """Layer-1 context management: keep the marked, archive + summarize the rest.

    When the total context size exceeds ``threshold`` (measured in characters by
    default), items marked ``important`` stay verbatim, and everything else is written
    to a durable archive file and replaced by a single summary pointer. The caller then
    builds the next context as ``kept + summary pointer``.

    The 0.8 (80%) threshold and the "important items survive, unmarked items compress"
    rule come directly from the study guide's compaction design.
    """

    DEFAULT_THRESHOLD_RATIO = 0.8

    def __init__(
        self,
        threshold: int,
        summarizer: Summarizer | None = None,
        size_of: Callable[[str], int] = len,
        threshold_ratio: float = DEFAULT_THRESHOLD_RATIO,
        protected_ids: set[str] | frozenset[str] | None = None,
    ) -> None:
        if threshold < 0:
            raise ValueError("threshold must be non-negative")
        if not 0.0 < threshold_ratio <= 1.0:
            raise ValueError("threshold_ratio must be in (0, 1]")
        self._threshold = threshold
        self._summarizer = summarizer or ExtractiveSummarizer()
        self._size_of = size_of
        self._threshold_ratio = threshold_ratio
        # Items bearing these ids are never archived, even when unmarked — they are the
        # goal/acceptance anchors that must survive compaction (D2).
        self._protected_ids = frozenset(protected_ids or ())

    def compact_window(
        self,
        items: Iterable[ContextItem],
        window_size: int,
        archive_dir: str | Path,
        archive_name: str,
        budget: int | None = None,
    ) -> CompactionResult:
        """Compaction triggered by crossing ``threshold_ratio`` (80%) of a window.

        This is the "80% cutoff" from the study guide: when the current context fills
        more than 80% of the window, keep the marked items and compress the rest.
        ``budget`` optionally constrains the recomposed output to a hard size.
        """
        if window_size <= 0:
            raise ValueError("window_size must be positive")
        material = list(items)
        total = sum(self._size_of(item.content) for item in material)
        if total <= int(self._threshold_ratio * window_size):
            return CompactionResult(
                kept=material,
                archived=[],
                summary="",
                archive_path="",
                compact_occurred=False,
            )
        # Reuse the core pass, but force compaction by using the actual total as a
        # threshold (the window check already determined we are over the ratio).
        return self._compact_material(material, Path(archive_dir), archive_name, budget=budget)

    def compact(
        self,
        items: Iterable[ContextItem],
        archive_dir: str | Path,
        archive_name: str,
        budget: int | None = None,
    ) -> CompactionResult:
        material = list(items)
        total = sum(self._size_of(item.content) for item in material)

        # Under the cutoff: leave everything as-is, no archive, no summary pointer.
        if total <= self._threshold:
            return self._unchanged(material)

        return self._compact_material(material, Path(archive_dir), archive_name, budget=budget)

    def _unchanged(self, material: list[ContextItem]) -> CompactionResult:
        return CompactionResult(
            kept=material,
            archived=[],
            summary="",
            archive_path="",
            compact_occurred=False,
        )

    def _compact_material(
        self,
        material: list[ContextItem],
        archive_dir: Path,
        archive_name: str,
        budget: int | None = None,
    ) -> CompactionResult:
        kept = [item for item in material if item.important or item.id in self._protected_ids]
        archived = [item for item in material if item not in kept]

        archive_path = self._write_archive(archived, archive_dir, archive_name)
        summary = self._summarizer.summarize(archived)

        if budget is not None:
            kept, summary = self._fit_budget(kept, summary, budget)

        return CompactionResult(
            kept=kept,
            archived=archived,
            summary=summary,
            archive_path=str(archive_path),
            compact_occurred=True,
        )

    def _fit_budget(
        self, kept: list[ContextItem], summary: str, budget: int
    ) -> tuple[list[ContextItem], str]:
        """Constrain ``kept + summary`` to ``budget`` (D1).

        When the important (non-protected) items alone overflow the budget, they are folded
        into the summary; the summary is then truncated if it still exceeds the budget.
        Protected anchors (D2) are kept verbatim; if only they remain and still overflow,
        the overshoot is accepted as the price of a hard anchor.
        """
        total = sum(self._size_of(item.content) for item in kept) + self._size_of(summary)
        if total <= budget:
            return kept, summary
        # Over budget: fold the important-but-unprotected items into the summary, keeping
        # only protected anchors verbatim, then truncate the summary to the budget.
        protected = [item for item in kept if item.id in self._protected_ids]
        foldable = [item for item in kept if item.id not in self._protected_ids]
        if foldable:
            summary = (summary + "\n" + self._summarizer.summarize(foldable)).strip()
            kept = protected
        remaining = budget - sum(self._size_of(item.content) for item in kept)
        if remaining > 0:
            summary = summary[:remaining]
        return kept, summary

    def _write_archive(
        self, items: list[ContextItem], archive_dir: Path, archive_name: str
    ) -> Path:
        archive_dir.mkdir(parents=True, exist_ok=True)
        path = archive_dir / archive_name
        payload = {
            "items": [
                {
                    "id": item.id,
                    "content": item.content,
                    "source": item.source,
                    "important": item.important,
                }
                for item in items
            ]
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
