"""Demo of hippocampus long-term memory.

Run:
    py -3 examples/hippocampus_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hippocampus import Hippocampus, HippocampusStore


def main() -> None:
    root = Path(__file__).with_name("hippocampus_memory")
    memory = Hippocampus(HippocampusStore(root))

    # Task 1: record a trajectory, indexing important content.
    traj = memory.start_trajectory("bug-42")
    memory.record_step(traj, "reproduce", "crash on null", "null deref in parser")
    memory.record_step(traj, "fix", "added guard", "always guard pointer deref")

    # Task 2: learn a fact, then correct it (delete wrong, learn right).
    memory.learn("deploy", "use --force", correct=True, evidence="first guess")
    memory.unlearn("deploy")
    memory.correct("deploy", "use --verify-first")

    print("=" * 60)
    replay = memory.replay("bug-42")
    print("Replay important lines:")
    for line in replay.important_lines:
        print(f"  - {line}")
    print("Retrospective (correct facts):")
    for fact in memory.retrospective():
        print(f"  - {fact.key} = {fact.value}")
    print("=" * 60)

    assert memory.get("deploy").value == "use --verify-first"
    assert replay.important_lines == [
        "null deref in parser",
        "always guard pointer deref",
    ]
    print("Done.")


if __name__ == "__main__":
    main()
