"""Adapters that route maker/checker through a ToolRegistry permission gate.

This closes the "last layer of composition" gap: instead of passing bare callables to
GoalLoopRunner, the maker and checker are registered as tools with permission labels,
and every round the registry enforces least privilege + schema validation before the
handler runs.
"""

from __future__ import annotations

from typing import Callable

from goal_loop.models import CheckerOutput, GoalSpec, LoopState, MakerOutput
from tool_registry import Permission, ToolRegistry, ToolResult, ToolSpec


class RegisteredMaker:
    """A maker whose work is a registered, permission-gated tool call."""

    def __init__(
        self,
        registry: ToolRegistry,
        tool_name: str,
        handler: Callable[..., MakerOutput],
    ) -> None:
        self._registry = registry
        self._tool_name = tool_name
        registry.register(
            ToolSpec(
                name=tool_name,
                description="maker implementation step",
                permission=Permission.WRITE,
                parameters_schema={
                    "type": "object",
                    "required": ["objective"],
                    "properties": {"objective": {"type": "string"}},
                },
            ),
            handler,
        )
        registry.enable(tool_name, Permission.WRITE)

    def __call__(self, spec: GoalSpec, state: LoopState, steering: str) -> MakerOutput:
        result: ToolResult = self._registry.call(self._tool_name, {"objective": spec.objective})
        if not result.ok:
            return MakerOutput(
                summary=f"maker tool blocked: {result.error}",
                tokens_used=0,
                ok=False,
            )
        return result.output


class RegisteredChecker:
    """A checker whose verdict is a registered, permission-gated tool call."""

    def __init__(
        self,
        registry: ToolRegistry,
        tool_name: str,
        handler: Callable[..., CheckerOutput],
    ) -> None:
        self._registry = registry
        self._tool_name = tool_name
        registry.register(
            ToolSpec(
                name=tool_name,
                description="independent checker verdict",
                permission=Permission.READ,
                parameters_schema={
                    "type": "object",
                    "required": ["summary"],
                    "properties": {"summary": {"type": "string"}},
                },
            ),
            handler,
        )
        registry.enable(tool_name, Permission.READ)

    def __call__(self, spec: GoalSpec, output: MakerOutput) -> CheckerOutput:
        result: ToolResult = self._registry.call(self._tool_name, {"summary": output.summary})
        if not result.ok:
            from goal_loop.models import Verdict

            return CheckerOutput(verdict=Verdict.FAIL, tokens_used=0)
        return result.output
