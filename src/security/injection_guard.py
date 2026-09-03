"""InjectionGuard: block prompt-injection that overrides the harness gate (CWE-77).

Anchored by constitution principle SEC-05. The guard inspects untrusted text and
flags the classic "ignore your instructions" overrides and secret-dump redirects.
It is deliberately narrow so a benign instruction is not misflagged, and it never
executes anything itself (no ``eval``/``exec`` in this module).
"""

from __future__ import annotations

from typing import Iterable


class InjectionGuard:
    """Decide whether free text contains a prompt-injection override.

    Detection is a case-insensitive substring scan over a narrow marker set.
    Fail-closed means the *caller* treats a hit as a refusal; the guard itself is
    read-only and returns a plain bool.
    """

    markers: tuple[str, ...]

    def __init__(
        self,
        markers: Iterable[str] = (
            "ignore all previous",
            "ignore all prior",
            "forget your instructions",
            "print the system",
        ),
    ) -> None:
        self.markers = tuple(m.lower() for m in markers)

    def detect_injection(self, text: str) -> bool:
        """Return True when ``text`` contains a known harness-override marker."""
        lowered = (text or "").lower()
        return any(marker in lowered for marker in self.markers)
