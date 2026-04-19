from __future__ import annotations

from simple_agent.schemas import AgentAction, ToolResult
from simple_agent.tools.registry import ToolRegistry


class Executor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, action: AgentAction) -> ToolResult:
        if action.type != "tool_call":
            return ToolResult(
                success=False,
                tool="",
                error="Not a tool_call action",
            )

        tool_name = action.tool or ""
        tool = self._registry.get(tool_name)

        if tool is None:
            return ToolResult(
                success=False,
                tool=tool_name,
                args=action.args,
                error=f"Unknown tool: '{tool_name}'",
            )

        try:
            output = tool.run(**action.args)
            return ToolResult(
                success=True,
                tool=tool_name,
                args=action.args,
                output=output,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                tool=tool_name,
                args=action.args,
                error=str(e),
            )
