"""Model adapter for the real-LLM eval suite.

Two API formats are normalized behind ``generate``: Anthropic-compatible (deepseek,
grok, minimax) and OpenAI-compatible (kimi). The thinking-model text extraction differs
per format, and token accounting is ``input + output`` (never ``- cache_read``) because
the llm-proxy reports cache buckets as non-overlapping.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """One model under test: wire id, endpoint, key env, and API format."""

    key: str
    model_id: str
    base_url: str
    api_key_env: str
    format: str  # "anthropic" | "openai"


@dataclass(frozen=True, slots=True)
class LLMReply:
    """A normalized model reply: text plus honest tokens and wall-clock latency."""

    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


MODELS: list[ModelSpec] = [
    ModelSpec(
        "deepseek-v4-pro",
        "deepseek/deepseek-v4-pro",
        "https://llm-proxy.tapsvc.com",
        "ANTHROPIC_AUTH_TOKEN",
        "anthropic",
    ),
    ModelSpec(
        "deepseek-v4-flash",
        "deepseek/deepseek-v4-flash",
        "https://llm-proxy.tapsvc.com",
        "ANTHROPIC_AUTH_TOKEN",
        "anthropic",
    ),
    ModelSpec(
        "grok-4.6",
        "x-ai-grok/grok-4.6",
        "https://llm-proxy.tapsvc.com",
        "ANTHROPIC_AUTH_TOKEN",
        "anthropic",
    ),
    ModelSpec(
        "minimax-m3",
        "MiniMax-M3",
        "https://api.minimaxi.com/anthropic",
        "MINIMAX_API_KEY",
        "anthropic",
    ),
    ModelSpec(
        "kimi-k2-turbo-preview",
        "kimi-k2-turbo-preview",
        "https://api.kimi.com/coding/v1",
        "KIMI_CODE_API_KEY",
        "openai",
    ),
    # glm is quota-blocked (code 1113 "no resource package"); re-add when quota returns:
    # ModelSpec("glm", "glm-4.6", "https://open.bigmodel.cn/api/paas/v4/", "GLM_API_KEY", "openai"),
]


def _load_env() -> dict[str, str]:
    """Read ``.env`` and merge with the process env (process env wins).

    The newer keys (KIMI_*, GLM_*, MINIMAX_*) live in ``.env``, not the shell profile,
    so ``os.environ`` alone is missing them.
    """
    env: dict[str, str] = {}
    if _DOTENV_PATH.exists():
        for line in _DOTENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


def _extract_anthropic_text(content) -> str:
    """Pull text blocks only; a thinking model leads with a ThinkingBlock (.thinking)."""
    return "".join(b.text for b in content if b.type == "text")


def _extract_openai_text(message) -> str:
    """OpenAI-compatible: the answer is in ``content``; reasoning is a sibling field."""
    return message.content or ""


def _anthropic(spec: ModelSpec, key: str, prompt: str, max_tokens: int, system: Optional[str]):
    import anthropic

    client = anthropic.Anthropic(base_url=spec.base_url, api_key=key)
    kwargs = {
        "model": spec.model_id,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return (
        _extract_anthropic_text(resp.content),
        resp.usage.input_tokens,
        resp.usage.output_tokens,
    )


def _openai(spec: ModelSpec, key: str, prompt: str, max_tokens: int, system: Optional[str]):
    from openai import OpenAI

    client = OpenAI(base_url=spec.base_url, api_key=key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(model=spec.model_id, max_tokens=max_tokens, messages=messages)
    message = resp.choices[0].message
    return (
        _extract_openai_text(message),
        resp.usage.prompt_tokens,
        resp.usage.completion_tokens,
    )


def generate(
    spec: ModelSpec,
    prompt: str,
    *,
    max_tokens: int = 256,
    system: Optional[str] = None,
) -> LLMReply:
    """Call one model and normalize the result into an ``LLMReply``."""
    env = _load_env()
    key = env.get(spec.api_key_env)
    if not key:
        raise KeyError(f"missing API key env {spec.api_key_env!r}")
    start = time.monotonic()
    if spec.format == "anthropic":
        text, i, o = _anthropic(spec, key, prompt, max_tokens, system)
    elif spec.format == "openai":
        text, i, o = _openai(spec, key, prompt, max_tokens, system)
    else:
        raise ValueError(f"unknown format {spec.format!r}")
    return LLMReply(text=text, input_tokens=i, output_tokens=o, latency_ms=(time.monotonic() - start) * 1000)
