from __future__ import annotations

import shlex
import subprocess
from typing import Sequence

from goal_loop.models import VerificationResult


_STDOUT_LIMIT = 4000
_STDERR_LIMIT = 4000


class CommandVerifier:
    """Run a verification command and return structured evidence.

    Commands run with ``shell=False``. A string command is split with ``shlex.split``
    into an argv list first, so ``"python -m pytest"`` works on every platform without
    letting shell metacharacters execute. The trust boundary is the human-authored
    ``GoalSpec``: commands listed there are considered intentional.
    """

    def __init__(self, timeout_s: int = 60) -> None:
        self._timeout_s = timeout_s

    def run(self, command: str | Sequence[str]) -> VerificationResult:
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        display = command if isinstance(command, str) else " ".join(command)
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
            return VerificationResult(
                command=display,
                returncode=proc.returncode,
                timed_out=False,
                stdout=proc.stdout[-_STDOUT_LIMIT:],
                stderr=proc.stderr[-_STDERR_LIMIT:],
            )
        except subprocess.TimeoutExpired as exc:
            return VerificationResult(
                command=display,
                returncode=-1,
                timed_out=True,
                stdout=(exc.stdout or "")[-_STDOUT_LIMIT:],
                stderr=(exc.stderr or "")[-_STDERR_LIMIT:],
            )
        except OSError as exc:
            return VerificationResult(
                command=display,
                returncode=127,
                timed_out=False,
                stdout="",
                stderr=f"failed to run command: {exc}",
            )
