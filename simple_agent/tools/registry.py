from __future__ import annotations

from simple_agent.tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def list_specs(self) -> list[dict]:
        return [tool.spec().model_dump() for tool in self._tools.values()]

    def tool_descriptions_for_prompt(self) -> str:
        lines: list[str] = []
        for tool in self._tools.values():
            spec = tool.spec()
            params = ", ".join(
                f"{k} ({v})" for k, v in spec.args_schema.items()
            )
            lines.append(f"- {spec.name}: {spec.description}. Parameters: {params}")
        return "\n".join(lines)
