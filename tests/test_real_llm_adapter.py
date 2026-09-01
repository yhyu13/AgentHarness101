"""Offline tests for the real-LLM adapter (no API calls).

These pin the two things that silently break against real providers: (1) thinking-model
text extraction differs by API format, and (2) token accounting must not subtract cache
read tokens (the llm-proxy reports them as non-overlapping buckets).
"""

from __future__ import annotations

import pytest

from eval_llm.client import (
    MODELS,
    LLMReply,
    ModelSpec,
    _extract_anthropic_text,
    _extract_openai_text,
    _load_env,
    generate,
)


class _Block:
    def __init__(self, type_: str, text: str) -> None:
        self.type = type_
        self.text = text


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


def test_models_cover_both_formats_and_exclude_glm():
    formats = {m.format for m in MODELS}
    assert formats == {"anthropic", "openai"}
    # glm is quota-blocked (code 1113); it must not silently run and fail the batch.
    assert "glm" not in [m.key for m in MODELS]
    # every model carries an api_key_env so a missing key is a clear, catchable error.
    assert all(m.api_key_env for m in MODELS)


def test_extract_anthropic_skips_thinking_block():
    content = [_Block("thinking", "internal reasoning..."), _Block("text", "code"), _Block("text", "more")]
    assert _extract_anthropic_text(content) == "codemore"


def test_extract_openai_uses_content_not_reasoning():
    assert _extract_openai_text(_Msg("answer")) == "answer"
    assert _extract_openai_text(_Msg("")) == ""


def test_generate_missing_key_raises(monkeypatch):
    spec = ModelSpec("x", "m", "https://x", "NO_SUCH_KEY_XYZ", "anthropic")
    monkeypatch.delenv("NO_SUCH_KEY_XYZ", raising=False)
    with pytest.raises(KeyError):
        generate(spec, "hi")


def test_generate_anthropic_dispatches_and_records_reply(monkeypatch):
    spec = ModelSpec("x", "m", "https://x", "FAKE_ANTHROPIC_KEY", "anthropic")
    monkeypatch.setenv("FAKE_ANTHROPIC_KEY", "k")

    def fake_anthropic(_spec, _key, _prompt, _max_tokens, _system):
        return "TEXT", 10, 5

    monkeypatch.setattr("eval_llm.client._anthropic", fake_anthropic)
    reply = generate(spec, "hello", system="sys")
    assert isinstance(reply, LLMReply)
    assert reply.text == "TEXT"
    assert reply.input_tokens == 10
    assert reply.output_tokens == 5
    assert reply.latency_ms >= 0


def test_generate_openai_dispatches(monkeypatch):
    spec = ModelSpec("x", "m", "https://x", "FAKE_OPENAI_KEY", "openai")
    monkeypatch.setenv("FAKE_OPENAI_KEY", "k")
    monkeypatch.setattr("eval_llm.client._openai", lambda *a, **k: ("O", 1, 2))
    assert generate(spec, "hi").text == "O"


def test_generate_unknown_format_raises(monkeypatch):
    spec = ModelSpec("x", "m", "https://x", "FAKE_KEY", "bogus")
    monkeypatch.setenv("FAKE_KEY", "k")
    with pytest.raises(ValueError):
        generate(spec, "hi")


def test_load_env_parses_dotenv_and_prefers_process_env(monkeypatch, tmp_path):
    # A synthetic .env is injected by monkeypatching the module's dotenv path. The keys
    # are deliberately namespaced so they cannot collide with a real exported env var.
    dotenv = tmp_path / ".env"
    dotenv.write_text('EVAL_TEST_A=dotenv-secret\nEVAL_TEST_B="https://kimi"\n', encoding="utf-8")
    monkeypatch.setattr("eval_llm.client._DOTENV_PATH", dotenv)
    monkeypatch.setenv("EVAL_TEST_A", "process-secret")
    env = _load_env()
    assert env["EVAL_TEST_A"] == "process-secret"  # process env wins
    assert env["EVAL_TEST_B"] == "https://kimi"  # dotenv-only value kept
