from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


# Secret-shaped substrings that should never be written to disk. These are deliberately
# broad-and-opinionated: it is cheaper to over-redact a benign string than to leak an API
# key into an append-only session log (E4).
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:sk|rk|pk|ak|ghp|gho|ghu|ghs|xox[baprs]|eyj)[-_a-z0-9]{8,}\b"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]{8,}"),
    re.compile(
        r"(?i)(?:api[_-]?key|token|password|passwd|secret|access[_-]?key|auth)\s*[:=]\s*[\"']?[a-z0-9._/-]{8,}"
    ),
)


def _redact_text(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("***REDACTED***", text)
    return text


def redact_value(value: Any) -> Any:
    """Recursively mask secret-shaped values in trace payloads.

    Strings are matched against secret patterns; mappings and sequences are walked so a
    key nested anywhere in a prompt/tool payload is masked before it is persisted.
    """
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {key: redact_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [redact_value(val) for val in value]
    if isinstance(value, tuple):
        return tuple(redact_value(val) for val in value)
    return value


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """One immutable event in the append-only session log."""

    seq: int
    event_type: str
    payload: Any


class TraceLog:
    """Layer-6 observability: append-only log with byte-level replay.

    Every event is appended as one JSON line. Because events are immutable and written
    in sequence, the exact messages an agent saw can be reconstructed byte-for-byte from
    the log — the first industrial invariant (append-only session log).
    """

    def __init__(self, path: str | Path, redact_secrets: bool = True) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._next_seq = self._read_next_seq()
        self._redact_secrets = redact_secrets

    def append(self, event_type: str, payload: Any) -> TraceEvent:
        if self._redact_secrets:
            payload = redact_value(payload)
        event = TraceEvent(seq=self._next_seq, event_type=event_type, payload=payload)
        line = json.dumps(
            {"seq": event.seq, "type": event.event_type, "payload": event.payload},
            ensure_ascii=False,
        )
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._next_seq += 1
        return event

    def replay(self) -> list[TraceEvent]:
        """Reconstruct the full event sequence byte-for-byte from the log."""
        if not self._path.exists():
            return []
        events = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            events.append(
                TraceEvent(seq=data["seq"], event_type=data["type"], payload=data["payload"])
            )
        return events

    def messages(self, event_type: str) -> list[Any]:
        return [e.payload for e in self.replay() if e.event_type == event_type]

    @contextmanager
    def span(self, event_type: str, **payload: Any) -> Iterator[None]:
        """Record the wall-clock duration of a code block as one trace event.

        The event is appended once on exit (even on exception), with a ``duration_ms``
        field measured in milliseconds. Extra keyword args ride along in the payload.
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            payload["duration_ms"] = round((time.perf_counter() - start) * 1000, 3)
            self.append(event_type, payload)

    def _read_next_seq(self) -> int:
        events = self.replay()
        return (max((e.seq for e in events), default=-1)) + 1
