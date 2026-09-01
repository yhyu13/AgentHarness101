from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PathPolicy:
    """Filesystem write isolation at the path level (portable, fail-closed).

    A write target is allowed only if it resolves to a location inside one of the
    ``allow_roots``. The check is pure ``pathlib`` and runs identically on every OS.
    Real syscall-level isolation (seccomp/Landlock, network egress, fork) is OS-gated
    and NOT provided here — this layer is the portable floor beneath it: an empty
    allowlist rejects everything, and ``..`` traversal is collapsed by ``resolve()``
    before the containment check.
    """

    allow_roots: tuple[Path, ...]

    def __init__(self, allow_roots: Iterable[str | Path] = ()) -> None:
        roots = tuple(Path(r).resolve() for r in allow_roots)
        object.__setattr__(self, "allow_roots", roots)

    def allows_write(self, target: str | Path) -> bool:
        resolved = Path(target).resolve()
        return any(self._is_within(resolved, root) for root in self.allow_roots)

    @staticmethod
    def _is_within(target: Path, root: Path) -> bool:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False
