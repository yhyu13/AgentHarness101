"""Quantitative tests for the thinking benchmark harness (no API key needed).

These pin two layers with hand-computed expected values:
1. The wire contract — turning thinking OFF omits the ``thinking`` param entirely
   (the Anthropic-endpoint default = disabled), turning it ON sends ``adaptive``.
2. The statistics layer — ``stats`` (mean/variance/stddev) and ``compare`` (delta/%
   vs a baseline) match independently computed numbers.

Real token and wall-clock savings need a MiniMax key and live in
``examples/thinking_benchmark.py``; those numbers are marked `待确认` here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

import thinking_benchmark as tb


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = None


class _FakeResp:
    def __init__(self, usage) -> None:
        self.usage = usage


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResp(_FakeUsage(input_tokens=10, output_tokens=5))


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_stats_matches_hand_computed_values() -> None:
    s = tb.stats([1, 2, 3])
    assert s["n"] == 3
    assert abs(s["mean"] - 2.0) < 1e-9
    assert abs(s["variance"] - (2 / 3)) < 1e-9
    assert abs(s["stddev"] - (2 / 3) ** 0.5) < 1e-9


def test_stats_empty_returns_none() -> None:
    s = tb.stats([])
    assert s["n"] == 0
    assert s["mean"] is None
    assert s["variance"] is None
    assert s["stddev"] is None


def test_compare_delta_and_pct_against_baseline() -> None:
    # off mean=2 vs on mean=10 -> delta=-8, -80%
    c = tb.compare(tb.stats([1, 2, 3]), tb.stats([10, 10, 10]), "output_tokens")
    assert c["metric"] == "output_tokens"
    assert abs(c["delta"] - (-8.0)) < 1e-9
    assert abs(c["delta_pct"] - (-80.0)) < 1e-9


def test_thinking_off_omits_the_param_entirely() -> None:
    client = _FakeClient()
    out = tb.run_round(client, "MiniMax-M3", "hi", thinking=None)
    assert "thinking" not in client.messages.calls[0]
    assert out["input_tokens"] == 10
    assert out["output_tokens"] == 5
    assert out["wall_ms"] >= 0


def test_thinking_on_sends_adaptive() -> None:
    client = _FakeClient()
    tb.run_round(client, "MiniMax-M3", "hi", thinking={"type": "adaptive"})
    assert client.messages.calls[0]["thinking"] == {"type": "adaptive"}
