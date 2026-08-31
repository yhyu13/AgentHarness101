from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Result of a sandboxed command execution."""

    ok: bool
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    blocked: bool = False
    reason: str = ""


class Sandbox:
    """Layer-3 execution environment: fail-closed command execution.

    The two industrial invariants are enforced here:
    1. **Fail-closed**: if no backend is configured, ``run`` refuses with
       ``SANDBOX_UNAVAILABLE`` instead of executing bare.
    2. **Command allowlist**: only commands on the explicit allowlist run; anything else
       is blocked before launch. Commands run with ``shell=False`` so metacharacters
       cannot smuggle additional commands through a string.
    """

    def __init__(
        self,
        allowlist: set[str] | list[str] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._allowlist = set(allowlist or [])
        self._timeout_s = timeout_s

    @property
    def available(self) -> bool:
        """A sandbox is available only when a non-empty allowlist is configured."""
        return bool(self._allowlist)

    def run(self, command: str | list[str]) -> SandboxResult:
        argv = command if isinstance(command, list) else command.split()
        if not argv:
            return self._blocked("empty command")
        if not self.available:
            return SandboxResult(
                ok=False,
                returncode=-1,
                stdout="",
                stderr="",
                timed_out=False,
                blocked=True,
                reason="SANDBOX_UNAVAILABLE",
            )
        if argv[0] not in self._allowlist:
            return self._blocked(f"command not allowlisted: {argv[0]}")

        try:
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
            return SandboxResult(
                ok=proc.returncode == 0,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                ok=False,
                returncode=-1,
                stdout=(exc.stdout or ""),
                stderr=(exc.stderr or ""),
                timed_out=True,
            )
        except OSError as exc:
            return SandboxResult(
                ok=False,
                returncode=127,
                stdout="",
                stderr=f"failed to launch: {exc}",
                timed_out=False,
            )

    def _blocked(self, reason: str) -> SandboxResult:
        return SandboxResult(
            ok=False,
            returncode=-1,
            stdout="",
            stderr="",
            timed_out=False,
            blocked=True,
            reason=reason,
        )
