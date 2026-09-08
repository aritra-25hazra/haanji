"""The tool layer.

Every action the agent can take is declared here with three properties the
rest of the engine depends on:

``read_only``
    the call has no effect the caller could observe later. Only read-only
    tools may be speculated. This is the purity condition of Speculative
    Turn Execution, and it is enforced in the registry rather than trusted
    to the model.

``requires_confirmation``
    the call changes the tenant's world and must not happen until the caller
    has said yes to a specific, repeated summary. The Pramaan Ledger refuses
    to seal such an action without the proof.

``ledgered``
    the call produces a signed receipt in the tamper-evident chain.
"""
from __future__ import annotations
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..models import ToolResult


class ToolError(RuntimeError):
    pass


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, str]
    handler: Callable[..., Any]
    read_only: bool = True
    requires_confirmation: bool = False
    ledgered: bool = False
    nominal_ms: float = 0.0
    required: list[str] = field(default_factory=list)

    def schema(self) -> dict[str, Any]:
        """The JSON-schema-shaped description a language model would receive."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v}
                               for k, v in self.parameters.items()},
                "required": self.required,
            },
            "x-haanji": {"read_only": self.read_only,
                         "requires_confirmation": self.requires_confirmation,
                         "ledgered": self.ledgered},
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.read_only and tool.ledgered:
            raise ToolError(f"'{tool.name}' cannot be both read-only and ledgered")
        if tool.requires_confirmation and tool.read_only:
            raise ToolError(f"'{tool.name}' is read-only, so confirmation is meaningless")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(f"unknown tool '{name}'")
        return self._tools[name]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def is_read_only(self, name: str) -> bool:
        """Used by the speculation engine. Unknown tools are never speculated."""
        tool = self._tools.get(name)
        return bool(tool and tool.read_only)

    def requires_confirmation(self, name: str) -> bool:
        tool = self._tools.get(name)
        return bool(tool and tool.requires_confirmation)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    async def execute(self, name: str, args: dict[str, Any]) -> Any:
        """Run a tool. Argument errors are returned, not raised, so one bad
        call cannot end a live phone call."""
        tool = self.get(name)
        try:
            result = tool.handler(**args)
            if inspect.isawaitable(result):
                result = await result
            return result
        except TypeError as exc:
            return ToolResult(name, ok=False, error=f"bad arguments: {exc}")
        except Exception as exc:                      # noqa: BLE001 - boundary
            return ToolResult(name, ok=False, error=str(exc))


from .builtin import build_registry            # noqa: E402  (cyclic by design)

__all__ = ["Tool", "ToolRegistry", "ToolError", "build_registry"]
