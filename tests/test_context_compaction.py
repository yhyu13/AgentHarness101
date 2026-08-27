"""Tests for layer-1 context management (80% cutoff compaction)."""

from pathlib import Path

import pytest

from context_compaction import ContextCompactor, ContextItem


def item(id: str, content: str, important: bool = False, source: str = "") -> ContextItem:
    return ContextItem(id=id, content=content, important=important, source=source)


def test_no_compaction_under_threshold(tmp_path: Path) -> None:
    compactor = ContextCompactor(threshold=100)
    result = compactor.compact(
        [item("a", "short"), item("b", "also short")], tmp_path, "archive.json"
    )
    assert not result.compact_occurred
    assert result.kept == [item("a", "short"), item("b", "also short")]
    assert result.archived == []
    assert result.summary == ""


def test_compaction_keeps_important_and_archives_rest(tmp_path: Path) -> None:
    compactor = ContextCompactor(threshold=10)
    items = [
        item("a", "important content", important=True, source="sys"),
        item("b", "long unmarked content here"),
        item("c", "another unmarked item"),
    ]
    result = compactor.compact(items, tmp_path, "archive.json")

    assert result.compact_occurred
    assert [i.id for i in result.kept] == ["a"]
    assert [i.id for i in result.archived] == ["b", "c"]
    assert result.summary
    assert "Archived 2" in result.summary
    assert Path(result.archive_path).exists()


def test_archive_is_json_and_roundtrips(tmp_path: Path) -> None:
    import json

    compactor = ContextCompactor(threshold=0)
    result = compactor.compact(
        [item("x", "unmarked", source="tool")], tmp_path, "archive.json"
    )
    data = json.loads(Path(result.archive_path).read_text(encoding="utf-8"))
    assert data["items"][0]["id"] == "x"
    assert data["items"][0]["source"] == "tool"


def test_summary_can_be_used_as_context_pointer(tmp_path: Path) -> None:
    compactor = ContextCompactor(threshold=5)
    items = [
        item("keep", "KEEP ME", important=True),
        item("drop", "DROP ME TO ARCHIVE"),
    ]
    result = compactor.compact(items, tmp_path, "a.json")

    # The caller builds the next context as kept + summary pointer.
    next_context = result.kept_content + [result.summary]
    assert "KEEP ME" in next_context[0]
    assert any("DROP" in part or "Archived" in part for part in next_context[1:])


def test_custom_size_function(tmp_path: Path) -> None:
    # Size measured in number of items, not characters.
    compactor = ContextCompactor(threshold=2, size_of=lambda content: 1)
    result = compactor.compact(
        [
            item("a", "x", important=True),
            item("b", "y"),
            item("c", "z"),
        ],
        tmp_path,
        "a.json",
    )
    assert result.compact_occurred
    assert [i.id for i in result.kept] == ["a"]
    assert [i.id for i in result.archived] == ["b", "c"]


def test_rejects_negative_threshold() -> None:
    with pytest.raises(ValueError):
        ContextCompactor(threshold=-1)


def test_window_80_percent_triggers_compaction(tmp_path: Path) -> None:
    compactor = ContextCompactor(threshold=0, threshold_ratio=0.8)
    # Window of 100 chars: 81 chars crosses 80%, 79 does not.
    over = [
        item("a", "x" * 81, important=True),
        item("b", "unmarked"),
    ]
    result = compactor.compact_window(over, window_size=100, archive_dir=tmp_path, archive_name="a.json")
    assert result.compact_occurred

    under = [item("a", "x" * 79, important=True)]
    result_under = compactor.compact_window(under, window_size=100, archive_dir=tmp_path, archive_name="b.json")
    assert not result_under.compact_occurred


def test_window_rejects_nonpositive(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ContextCompactor(threshold=0).compact_window([], window_size=0, archive_dir=tmp_path, archive_name="x")
