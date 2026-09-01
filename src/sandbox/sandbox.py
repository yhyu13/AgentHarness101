from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sandbox.path_policy import PathPolicy


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


# Minimal, safe environment passed to every sandboxed command. We keep only what a
# process needs to launch (PATH), find its home (HOME), and — on Windows — the system
# dirs that the standard library expects. Nothing else (API keys, tokens, parent
# credentials) is inherited.
_SAFE_ENV_KEYS = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "SystemRoot",
    "SystemDrive",
    "TEMP",
    "TMP",
    "PATHEXT",
    "COMSPEC",
    "LANG",
    "LC_ALL",
)


def _safe_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}


class Sandbox:
    """Layer-3 execution environment: fail-closed command execution.

    The industrial invariants enforced here:
    1. **Fail-closed**: if no backend is configured, ``run`` refuses with
       ``SANDBOX_UNAVAILABLE`` instead of executing bare.
    2. **Command allowlist**: only commands on the explicit allowlist run; anything else
       is blocked before launch. Commands run with ``shell=False`` so metacharacters
       cannot smuggle additional commands through a string.
    3. **Portable confinement**: an allowlisted command is confined to a working
       directory (``cwd``, defaulting to a path-policy root when one is given) and runs
       under a scrubbed environment. ``allows_write`` reports the path-policy boundary.

    Isolation is cooperative (an argv/command allowlist + cwd + pathlib containment), not
    OS-level — seccomp/Landlock/network-egress are unavailable and intentionally absent.
    """

    def __init__(
        self,
        allowlist: set[str] | list[str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | Path | None = None,
        path_policy: PathPolicy | None = None,
    ) -> None:
        self._allowlist = set(allowlist or [])
        self._timeout_s = timeout_s
        self._path_policy = path_policy or PathPolicy([])
        # If no explicit cwd, confine to the first path-policy root so relative writes
        # stay inside the declared boundary.
        self._cwd = (
            Path(cwd)
            if cwd is not None
            else (self._path_policy.allow_roots[0] if self._path_policy.allow_roots else None)
        )

    @property
    def available(self) -> bool:
        """A sandbox is available only when a non-empty allowlist is configured."""
        return bool(self._allowlist)

    def allows_write(self, target: str | Path) -> bool:
        """Report whether a target resolves inside the path-policy boundary."""
        return self._path_policy.allows_write(target)

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

        # Resolve a bare allowlisted name via PATH so we never launch an ambiguous or
        # cwd-shadowed executable. When the command is not on PATH, fall through to
        # subprocess.run, which reports the missing launcher as a launch OSError.
        resolved = shutil.which(argv[0])
        if resolved is not None:
            argv = [str(resolved), *argv[1:]]

        try:
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                cwd=str(self._cwd) if self._cwd is not None else None,
                env=_safe_env(),
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
