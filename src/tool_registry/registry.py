from __future__ import annotations

from typing import Any

from tool_registry.models import Permission, ToolRegistration, ToolResult, ToolSpec


class ToolRegistry:
    """Layer-2 tool management: register tools, bound permissions, enable selectively.

    The registry enforces least privilege: a tool cannot be called unless its permission
    is explicitly enabled for the current task, and parameters are validated against the
    tool's JSON schema (a missing/invalid field is rejected before the handler runs).
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}
        self._enabled: dict[str, set[Permission]] = {}

    def register(self, spec: ToolSpec, handler) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = ToolRegistration(spec=spec, handler=handler)

    def enable(self, name: str, permission: Permission) -> None:
        self._require(name)
        self._enabled.setdefault(name, set()).add(permission)

    def disable(self, name: str, permission: Permission) -> None:
        self._require(name)
        if name in self._enabled:
            self._enabled[name].discard(permission)

    def specs(self) -> list[ToolSpec]:
        return [reg.spec for reg in self._tools.values()]

    def call(self, name: str, parameters: dict[str, Any]) -> ToolResult:
        reg = self._require(name)
        if reg.spec.permission not in self._enabled.get(name, set()):
            return ToolResult(
                ok=False,
                error=(f"permission {reg.spec.permission.value} not enabled for tool {name}"),
            )

        validation_error = self._validate(reg.spec.parameters_schema, parameters)
        if validation_error:
            return ToolResult(ok=False, error=validation_error)

        try:
            return ToolResult(ok=True, output=reg.handler(**parameters))
        except Exception as exc:  # noqa: BLE001 - the harness must never let a tool crash the loop
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    def _require(self, name: str) -> ToolRegistration:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def _validate(self, schema: dict[str, Any], parameters: dict[str, Any]) -> str:
        if not schema:
            return ""
        required = schema.get("required", [])
        for key in required:
            if key not in parameters:
                return f"missing required parameter: {key}"
        properties = schema.get("properties", {})
        for key, spec in properties.items():
            if key not in parameters:
                continue
            value = parameters[key]
            expected = spec.get("type")
            if expected == "integer" and not isinstance(value, int):
                return f"parameter {key} must be an integer"
            if expected == "string" and not isinstance(value, str):
                return f"parameter {key} must be a string"
        return ""
