"""Cluster D tests: budget-constrained compaction (D1) and protected-anchor compaction (D2).

The default compactor keeps *every* important item verbatim and archives the rest. These
tests pin two hardening properties: the output can be constrained to a budget even when
the important set is large, and a caller can mark goal/acceptance anchors as protected so
they survive compaction even when they are not flagged important.
"""

from pathlib import Path

from context_compaction import ContextCompactor, ContextItem


def item(id: str, content: str, important: bool = False, source: str = "") -> ContextItem:
    return ContextItem(id=id, content=content, important=important, source=source)


class TestBudgetConstrainedCompaction:
    """D1: compaction can be asked to fit a budget, even when important items overflow."""

    def test_budget_folds_important_overflow(self, tmp_path: Path) -> None:
        compactor = ContextCompactor(threshold=10, size_of=len)
        items = [
            item("a", "IMPORTANT LONG " * 4, important=True),  # 60 chars of kept content
            item("b", "unmarked " * 6),  # 54 chars of archivable content
        ]
        result = compactor.compact(items, tmp_path, "a.json", budget=50)
        # Over budget: the important-but-unprotected overflow is folded into the summary
        # (and truncated if needed) so the recomposed context fits the budget.
        out = sum(len(i.content) for i in result.kept) + len(result.summary)
        assert result.compact_occurred
        assert out <= 50

    def test_budget_keeps_important_when_it_fits(self, tmp_path: Path) -> None:
        compactor = ContextCompactor(threshold=10, size_of=len)
        items = [
            item("a", "short important", important=True),
            item("b", "unmarked " * 6),
        ]
        result = compactor.compact(items, tmp_path, "a.json", budget=1000)
        assert result.compact_occurred
        assert [i.id for i in result.kept] == ["a"]
        assert sum(len(i.content) for i in result.kept) + len(result.summary) <= 1000

    def test_budget_none_preserves_legacy_behavior(self, tmp_path: Path) -> None:
        compactor = ContextCompactor(threshold=10)
        items = [
            item("a", "IMPORTANT LONG " * 4, important=True),
            item("b", "unmarked " * 6),
        ]
        result = compactor.compact(items, tmp_path, "a.json")
        assert [i.id for i in result.kept] == ["a"]  # important kept verbatim, no folding


class TestProtectedAnchorCompaction:
    """D2: goal/acceptance anchors marked protected survive even when unmarked."""

    def test_protected_unmarked_item_survives(self, tmp_path: Path) -> None:
        compactor = ContextCompactor(threshold=10, protected_ids={"goal-1"})
        items = [
            item("goal-1", "THE GOAL must never be archived", important=False),
            item("b", "unmarked " * 8),
        ]
        result = compactor.compact(items, tmp_path, "a.json")
        assert any(i.id == "goal-1" for i in result.kept)
        assert all(i.id != "goal-1" for i in result.archived)

    def test_protected_item_is_verbatim_when_budget_tight(self, tmp_path: Path) -> None:
        compactor = ContextCompactor(threshold=10, size_of=len, protected_ids={"goal-1"})
        items = [
            item("goal-1", "ANCHOR", important=False),
            item("b", "unmarked " * 8),
        ]
        result = compactor.compact(items, tmp_path, "a.json", budget=200)
        kept = result.kept_content
        assert kept[0] == "ANCHOR"  # verbatim, not summarized
