from __future__ import annotations

from simple_agent.tools.core.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def list_specs(self) -> list[dict]:
        return [tool.spec.model_dump() for tool in self._tools.values()]

    def tool_descriptions_for_prompt(self) -> str:
        lines: list[str] = []
        for tool in self._tools.values():
            s = tool.spec
            params = ", ".join(
                f"{k} ({v})" for k, v in s.input_schema.items()
            )
            lines.append(f"- {s.name}: {s.description}. Parameters: {params}")
        return "\n".join(lines)


def default_registry() -> ToolRegistry:
    from simple_agent.tools.read_file import ReadFileTool
    from simple_agent.tools.write_file import WriteFileTool
    from simple_agent.tools.bash import BashTool
    from simple_agent.tools.list_dir import ListDirTool
    from simple_agent.tools.glob import GlobTool
    from simple_agent.tools.grep import GrepTool
    from simple_agent.tools.edit_file import EditFileTool
    from simple_agent.tools.multi_edit import MultiEditTool

    registry = ToolRegistry()
    for cls in [
        ReadFileTool,
        WriteFileTool,
        BashTool,
        ListDirTool,
        GlobTool,
        GrepTool,
        EditFileTool,
        MultiEditTool,
    ]:
        registry.register(cls())
    return registry
