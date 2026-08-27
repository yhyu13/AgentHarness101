"""Tests for layer-4 hippocampus long-term memory."""

from pathlib import Path

from hippocampus import Hippocampus, HippocampusStore, MemoryFact


def test_trajectory_records_and_replays(tmp_path: Path) -> None:
    memory = Hippocampus(HippocampusStore(tmp_path))
    traj = memory.start_trajectory("task-1")
    memory.record_step(traj, "search", "found X", "X is the answer")
    memory.record_step(traj, "fix", "patched", "use fix A")

    replay = memory.replay("task-1")
    assert replay is not None
    assert replay.important_lines == ["X is the answer", "use fix A"]
    assert len(replay.trajectory.steps) == 2


def test_index_and_cache(tmp_path: Path) -> None:
    store = HippocampusStore(tmp_path)
    store.upsert_fact(MemoryFact(key="k1", value="important detail"))
    assert store.get_fact("k1").value == "important detail"
    assert store.read_cache("k1") == "important detail"
    assert (tmp_path / "memory_index.json").exists()


def test_learn_unlearn_correct(tmp_path: Path) -> None:
    memory = Hippocampus(HippocampusStore(tmp_path))
    memory.learn("a", "wrong value", correct=True)
    assert memory.get("a").value == "wrong value"

    # Delete the wrong fact.
    assert memory.unlearn("a")
    assert memory.get("a") is None

    # Learn the correct replacement.
    memory.correct("a", "right value")
    assert memory.get("a").value == "right value"


def test_retrospective_returns_only_correct(tmp_path: Path) -> None:
    memory = Hippocampus(HippocampusStore(tmp_path))
    memory.learn("good", "keep", correct=True)
    memory.learn("bad", "drop", correct=False)
    facts = memory.retrospective()
    assert [f.key for f in facts] == ["good"]


def test_replay_missing_returns_none(tmp_path: Path) -> None:
    memory = Hippocampus(HippocampusStore(tmp_path))
    assert memory.replay("nope") is None


def test_unlearn_clears_cache(tmp_path: Path) -> None:
    store = HippocampusStore(tmp_path)
    store.upsert_fact(MemoryFact(key="k", value="v"))
    assert store.read_cache("k") == "v"
    assert store.forget_fact("k")
    assert store.read_cache("k") is None
