from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ContextItem:
    """One unit of agent context (a message, tool result, document chunk, etc.).

    ``important`` is the user/LLM mark: items marked important are kept verbatim when
    the context crosses the cutoff; everything else is archived to disk and replaced
    by a summary pointer.
    """

    id: str
    content: str
    important: bool = False
    source: str = ""


@dataclass(frozen=True, slots=True)
class CompactionResult:
    """What a compaction pass produces.

    - ``kept``: important items preserved verbatim.
    - ``archived``: unmarked items moved out of context.
    - ``summary``: condensation of the archived items (caller feeds it back in).
    - ``archive_path``: on-disk location of the archived content.
    - ``compact_occurred``: False when under threshold, so the caller can skip the
      summary pointer entirely.
    """

    kept: list[ContextItem]
    archived: list[ContextItem]
    summary: str = ""
    archive_path: str = ""
    compact_occurred: bool = False

    @property
    def kept_content(self) -> list[str]:
        return [item.content for item in self.kept]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept": [item.__dict__ for item in self.kept],
            "archived": [item.__dict__ for item in self.archived],
            "summary": self.summary,
            "archive_path": self.archive_path,
            "compact_occurred": self.compact_occurred,
        }
