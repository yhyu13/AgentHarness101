"""CommandPolicy: reject shell-command injection (CWE-78).

Anchored by constitution principle SEC-04. The guard is fail-closed: only an
explicit argv list whose first element is allowlisted is permitted; a raw shell
string (the classic ``;`` / ``|`` injection vector) is always rejected.
"""

from __future__ import annotations

from typing import Iterable, Sequence


class CommandPolicy:
    """Decide whether a command invocation is allowed under an allowlist.

    A command must be presented as a sequence of unambiguous argv strings, never
    as a raw shell string (``shell=True`` style). An empty allowlist denies
    everything — the same fail-closed floor as :class:`PathPolicy`.
    """

    allowlist: tuple[str, ...]

    def __init__(self, allowlist: Iterable[str] = ()) -> None:
        self.allowlist = tuple(allowlist)

    def allows_command(self, command: str | Sequence[str]) -> bool:
        """Return True only for a non-empty argv list allowlisted by its program."""
        if isinstance(command, str):
            return False  # raw shell string is the injection vector
        argv = tuple(command)
        if not argv or not all(isinstance(a, str) and a for a in argv):
            return False
        if not self.allowlist:
            return False  # empty allowlist = deny all
        if argv[0] not in self.allowlist:
            return False
        return True
