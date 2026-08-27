from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class Permission(str, Enum):
    """Tool permission label for least-privilege decisions."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A registered tool: its name, permission label, and JSON schema."""

    name: str
    description: str
    permission: Permission
    parameters_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolRegistration:
    """A live tool binding its spec to a callable."""

    spec: ToolSpec
    handler: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A tool invocation result with a success flag and structured output."""

    ok: bool
    output: Any = None
    error: str = ""
