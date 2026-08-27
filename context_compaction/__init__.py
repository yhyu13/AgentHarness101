"""Layer-1 context management: keep the marked, archive + summarize the rest.

Implements the 80%-cutoff compaction design from the harness study guide:

1. During a conversation the LLM/user marks important content.
2. When context crosses the cutoff, marked content stays verbatim.
3. Unmarked content moves to a local compression document and is summarized.
4. The compression-document reference + summary re-enter the new context.
"""

from context_compaction.compactor import ContextCompactor
from context_compaction.models import CompactionResult, ContextItem
from context_compaction.summarizer import ExtractiveSummarizer, Summarizer

__all__ = [
    "ContextCompactor",
    "CompactionResult",
    "ContextItem",
    "ExtractiveSummarizer",
    "Summarizer",
]
