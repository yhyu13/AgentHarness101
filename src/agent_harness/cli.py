"""The ``ah`` / ``python -m agent_harness`` command line interface (F2).

``main`` is the entrypoint declared in ``[project.scripts]``. It exists to give a
fresh environment a zero-config way to confirm the harness is importable and to
name every layer — a post-install smoke that a ``pip install`` can run.
"""

from __future__ import annotations

import importlib
from typing import Sequence

# The eleven layer packages that make up the harness, in build order. This is the
# same set guarranted by tests/test_packaging.py:test_every_src_package_imports_standalone.
LAYERS: tuple[str, ...] = (
    "goal_persistence",
    "goal_loop",
    "context_compaction",
    "hippocampus",
    "tool_registry",
    "sandbox",
    "eval_harness",
    "observability",
    "safety",
    "cost_control",
    "faux_provider",
)


def main(argv: Sequence[str] | None = None) -> int:
    """Import every layer and print an ok line per package; returns process exit code."""
    for name in LAYERS:
        importlib.import_module(name)
        print(f"ok  {name}")
    print("agent-harness: all layers importable")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    raise SystemExit(main())
