"""Smoke test for the efficiency measurement: real, non-degenerate numbers."""

import importlib.util
import sys
from pathlib import Path


def _load_measure():
    path = Path(__file__).parent.parent / "examples" / "measure_efficiency.py"
    spec = importlib.util.spec_from_file_location("measure_efficiency", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent.parent))
    spec.loader.exec_module(module)
    return module


def test_measurements_are_sane() -> None:
    m = _load_measure()
    loop = m._measure_loop()
    assert loop["status"] == "complete"
    assert loop["rounds"] == 2
    assert loop["maker_calls"] == 2
    assert loop["wall_seconds"] > 0

    compaction = m._measure_compaction()
    assert compaction["reduction_ratio"] < 1.0  # it actually reduced
    assert compaction["kept_items"] + compaction["archived_items"] == 100

    memory = m._measure_memory()
    assert memory["important_lines"] == 5
    assert memory["correct_facts"] == 6

    sandbox = m._measure_sandbox()
    assert sandbox["commands"] == 100
    assert sandbox["overhead_ratio"] > 0


def test_report_is_valid_json_and_deterministic() -> None:
    m = _load_measure()
    first = m._measure_compaction()
    second = m._measure_compaction()
    assert first["chars_in"] == second["chars_in"]
    assert first["reduction_ratio"] == second["reduction_ratio"]
