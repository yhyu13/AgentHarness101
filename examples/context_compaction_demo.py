"""Demo of layer-1 context management (80% cutoff compaction).

Run:
    py -3 examples/context_compaction_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context_compaction import ContextCompactor, ContextItem


def main() -> None:
    # A small 100-char budget so the long items clearly exceed the 80% cutoff.
    compactor = ContextCompactor(threshold=100)
    items = [
        ContextItem(id="1", content="CRITICAL: the system prompt contract", important=True),
        ContextItem(id="2", content="verbatim transcript line that is long and noisy " * 5),
        ContextItem(id="3", content="another long tool output that can be summarized " * 5),
    ]

    archive = Path(__file__).with_name("compaction_archive")
    result = compactor.compact(items, archive, "archive.json")

    next_context = result.kept_content + [result.summary]
    print("=" * 60)
    print("Kept verbatim (important):")
    for line in result.kept_content:
        print(f"  - {line[:60]}")
    print("Summary pointer fed back into context:")
    print(f"  {result.summary.splitlines()[0]}")
    print("Archive:", result.archive_path)
    print("=" * 60)

    assert result.compact_occurred
    assert len(result.kept) == 1
    assert len(next_context) == 2  # kept + summary pointer
    print("Done.")


if __name__ == "__main__":
    main()
