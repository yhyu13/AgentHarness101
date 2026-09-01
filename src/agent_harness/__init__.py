"""Agent Harness 101 — top-level CLI package.

This package is the thin installable entrypoint for the harness. It only wires the
layer packages (goal_persistence, goal_loop, sandbox, …) behind a ``python -m
agent_harness`` / ``ah`` command; the real logic lives in each layer.
"""

from __future__ import annotations

__version__ = "0.1.0"
