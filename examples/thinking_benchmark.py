"""Quantitative benchmark: does turning off MiniMax-M3 thinking save tokens and time?

Runs N rounds with thinking OFF (the ``thinking`` param omitted, which is the
Anthropic-endpoint default = disabled) and N rounds with thinking ON
(``{"type": "adaptive"}``), then reports per-round mean, variance, and stddev for
output tokens and wall-clock, plus the OFF-vs-ON delta and percent.

This needs a MiniMax key. Run:

    $env:MINIMAX_API_KEY = "..."
    py -3 examples/thinking_benchmark.py --rounds 5
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import anthropic

MODEL = os.environ.get("ANTHROPIC_MODEL", "MiniMax-M3")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
API_KEY = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")

# A representative small task: deterministic, machine-verifiable, no real reasoning.
SMALL_TASK_PROMPT = (
    "Write a Python function `def answer(): return 42`. Only the code, no explanation."
)


def thinking_off() -> dict | None:
    """Omit the ``thinking`` param — the Anthropic-endpoint default (disabled)."""
    return None


def thinking_on() -> dict:
    """Explicitly enable MiniMax-M3 thinking blocks."""
    return {"type": "adaptive"}


def run_round(
    client, model: str, prompt: str, thinking: dict | None, max_tokens: int = 256
) -> dict:
    """One LLM call; return its real input/output tokens and wall-clock milliseconds."""
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if thinking is not None:
        kwargs["thinking"] = thinking

    t0 = time.perf_counter()
    resp = client.messages.create(**kwargs)
    wall_ms = (time.perf_counter() - t0) * 1000

    return {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "wall_ms": wall_ms,
    }


def stats(samples: list[float]) -> dict:
    """Return {n, mean, variance, stddev} using population variance (divide by n)."""
    n = len(samples)
    if n == 0:
        return {"n": 0, "mean": None, "variance": None, "stddev": None}
    mean = sum(samples) / n
    variance = sum((x - mean) ** 2 for x in samples) / n
    return {"n": n, "mean": mean, "variance": variance, "stddev": variance**0.5}


def compare(off_stats: dict, on_stats: dict, metric: str) -> dict:
    """OFF-minus-ON delta and percent for one metric; negative delta = OFF cheaper."""
    off = off_stats["mean"]
    on = on_stats["mean"]
    if off is None or on is None:
        return {
            "metric": metric,
            "off_mean": None,
            "on_mean": None,
            "delta": None,
            "delta_pct": None,
        }
    delta = off - on
    delta_pct = (delta / on * 100) if on else 0.0
    return {
        "metric": metric,
        "off_mean": off,
        "on_mean": on,
        "delta": delta,
        "delta_pct": delta_pct,
    }


def _collect(client, model: str, prompt: str, thinking, rounds: int) -> list[dict]:
    return [run_round(client, model, prompt, thinking) for _ in range(rounds)]


def _metric_stats(rows: list[dict], key: str) -> dict:
    return stats([r[key] for r in rows])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5, help="rounds per mode")
    parser.add_argument("--prompt", default=SMALL_TASK_PROMPT)
    args = parser.parse_args()

    if not API_KEY:
        print("Set MINIMAX_API_KEY (or ANTHROPIC_AUTH_TOKEN) to run this benchmark.")
        return

    client = anthropic.Anthropic(base_url=BASE_URL, api_key=API_KEY)
    off = _collect(client, MODEL, args.prompt, thinking_off(), args.rounds)
    on = _collect(client, MODEL, args.prompt, thinking_on(), args.rounds)

    print("=" * 72)
    print(f"thinking OFF vs ON | model={MODEL} | rounds={args.rounds} each")
    print("=" * 72)
    for metric, unit in (("output_tokens", "tok"), ("wall_ms", "ms"), ("input_tokens", "tok")):
        off_s = _metric_stats(off, metric)
        on_s = _metric_stats(on, metric)
        c = compare(off_s, on_s, metric)
        print(
            f"{metric:14s} off={off_s['mean']:.1f}±{off_s['stddev']:.1f} {unit}  "
            f"on={on_s['mean']:.1f}±{on_s['stddev']:.1f} {unit}  "
            f"delta={c['delta']:+.1f} ({c['delta_pct']:+.1f}%)"
        )
    print("=" * 72)
    print("negative delta = thinking OFF is cheaper/faster.")


if __name__ == "__main__":
    main()
