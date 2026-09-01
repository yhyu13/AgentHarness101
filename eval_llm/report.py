"""Report collector for the real-LLM eval suite.

Each ``ReportEntry`` is one (model, dimension) result. ``render_markdown`` turns the
collected entries into a flat table. Cost is computed from an explicitly-illustrative
price table — the numbers pin the calculator's determinism, not real vendor pricing
(vendor prices are 待确认 and belong in a live config).
"""

from __future__ import annotations

from dataclasses import dataclass

# Illustrative USD per 1k tokens (input, output). Placeholder — NOT real vendor prices.
ILLUSTRATIVE_PRICE_PER_1K: dict[str, tuple[float, float]] = {
    "deepseek-v4-pro": (1.00, 3.00),
    "deepseek-v4-flash": (0.10, 0.30),
    "grok-4.6": (1.00, 3.00),
    "minimax-m3": (1.00, 3.00),
    "kimi-k2-turbo-preview": (1.00, 3.00),
}

_HEADER = (
    "| model | dimension | test | status | tokens (in/out) | latency_ms | cost_usd | note |\n"
    "|---|---|---|---|---|---|---|---|\n"
)


@dataclass(frozen=True, slots=True)
class ReportEntry:
    model: str
    dimension: str
    test_id: str
    status: str  # pass | fail | skip
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    note: str = ""


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Illustrative USD cost. Unknown model returns 0.0 (cost is advisory, not fail-closed)."""
    price = ILLUSTRATIVE_PRICE_PER_1K.get(model)
    if price is None:
        return 0.0
    in_per_1k, out_per_1k = price
    return (input_tokens * in_per_1k + output_tokens * out_per_1k) / 1000.0


def render_markdown(entries: list[ReportEntry]) -> str:
    lines = [_HEADER]
    for e in entries:
        note = e.note.replace("|", "\\|")
        lines.append(
            f"| {e.model} | {e.dimension} | {e.test_id} | {e.status} | {e.input_tokens}/{e.output_tokens} "
            f"| {e.latency_ms:.1f} | {e.cost_usd:.4f} | {note} |\n"
        )
    return "".join(lines)
