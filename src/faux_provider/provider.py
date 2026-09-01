"""Deterministic scripted LLM provider for testing the goal loop.

This is the pi-style faux provider: it replaces exactly one boundary — "what the
LLM says" — and records every call as a first-class event. It contains no loop
state logic; the loop state machine stays in ``GoalLoopRunner``.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterator, Sequence

# A scripted step is either a fixed string or a dynamic factory that can read the
# context/state the maker received and decide what to say.
FauxResponseFactory = Callable[[Any, Any], str]
FauxResponseStep = str | FauxResponseFactory


class FauxProviderExhausted(RuntimeError):
    """Raised when the script queue is empty and the provider is called again.

    The contract is strict: a scripted provider refuses to improvise. If a test
    under-scripts (fewer responses than maker calls), this raises instead of
    silently returning an empty reply.
    """


class FauxProvider:
    """A FIFO queue of scripted replies plus a first-class event log.

    The only public ways to feed it are ``set_responses`` (replace the queue) and
    ``append_responses`` (extend it). Each call to ``generate``/``stream`` consumes
    exactly one step: a string is returned verbatim, a factory is called as
    ``factory(context, state)``.
    """

    def __init__(
        self,
        responses: Sequence[FauxResponseStep] | None = None,
        *,
        tokens_per_second: int | None = None,
    ) -> None:
        self._queue: list[FauxResponseStep] = []
        self._call_count = 0
        self._events: list[dict[str, Any]] = []
        self._tokens_per_second = tokens_per_second
        if responses is not None:
            self.set_responses(responses)

    # ---------------------------------------------------------------- scripting

    def set_responses(self, responses: Sequence[FauxResponseStep]) -> None:
        """Replace the script queue with ``responses``."""
        self._queue = list(responses)

    def append_responses(self, responses: Sequence[FauxResponseStep]) -> None:
        """Extend the existing script queue with ``responses``."""
        self._queue.extend(responses)

    def get_pending_response_count(self) -> int:
        """How many scripted steps have not yet been consumed."""
        return len(self._queue)

    @property
    def call_count(self) -> int:
        """How many times the provider has been called (consumed a step)."""
        return self._call_count

    # ------------------------------------------------------------------ events

    @property
    def events(self) -> list[dict[str, Any]]:
        """A copy of the recorded call events, in order."""
        return list(self._events)

    def events_of_type(self, event_type: str) -> list[dict[str, Any]]:
        """Call events filtered by their ``type`` field."""
        return [e for e in self._events if e.get("type") == event_type]

    # ---------------------------------------------------------------- respond

    def generate(self, prompt: str, *, context: Any = None, state: Any = None) -> str:
        """Consume the next scripted step and return its reply text.

        Raises ``FauxProviderExhausted`` when the queue is empty.
        """
        if not self._queue:
            raise FauxProviderExhausted(
                "FauxProvider script queue is empty: script one response per call"
            )
        self._call_count += 1
        step = self._queue.pop(0)
        if isinstance(step, str):
            text = step
        else:
            text = step(context, state)
        self._events.append(
            {
                "type": "call",
                "prompt": prompt,
                "response": text,
                "call_index": self._call_count,
            }
        )
        return text

    def stream(self, prompt: str, *, context: Any = None, state: Any = None) -> Iterator[str]:
        """Consume one step and yield its reply as chunks.

        With ``tokens_per_second`` unset, yields the whole reply as a single chunk.
        Otherwise yields whitespace-delimited tokens, rate-limited, so consumers can
        observe a partial/multi-chunk stream.
        """
        text = self.generate(prompt, context=context, state=state)
        tps = self._tokens_per_second
        if tps is None:
            yield text
            return
        words = text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            time.sleep(1.0 / tps)
