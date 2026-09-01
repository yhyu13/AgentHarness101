"""Offline tests for the real-LLM report collector (no API calls)."""

from __future__ import annotations

from eval_llm.report import ReportEntry, compute_cost, render_markdown


def _entry(**kw):
    defaults = dict(
        model="deepseek-v4-pro",
        dimension="metrics",
        test_id="t1",
        status="pass",
        input_tokens=100,
        output_tokens=50,
        latency_ms=6210.0,
        cost_usd=0.25,
        note="mean 6.21s",
    )
    defaults.update(kw)
    return ReportEntry(**defaults)


def test_render_markdown_has_header_and_rows():
    entries = [
        _entry(),
        _entry(model="kimi-k2-turbo-preview", dimension="redteam", status="skip", note="quota 1113"),
    ]
    md = render_markdown(entries)
    assert "| model |" in md
    assert "| test |" in md  # test_id is its own column, not folded into dimension
    assert "deepseek-v4-pro" in md
    assert "kimi-k2-turbo-preview" in md
    assert "skip" in md
    assert "quota 1113" in md


def test_render_markdown_empty_returns_header_only():
    md = render_markdown([])
    assert "| model |" in md
    assert "deepseek-v4-pro" not in md


def test_compute_cost_is_deterministic_and_illustrative():
    c1 = compute_cost("deepseek-v4-pro", 1000, 1000)
    c2 = compute_cost("deepseek-v4-pro", 1000, 1000)
    assert c1 == c2
    assert c1 > 0.0
