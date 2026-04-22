from __future__ import annotations

from simple_agent.schemas import ToolOutput
from simple_agent.tools.base import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the content of a text file"
    args_schema = {"path": "string - absolute path to the file"}

    async def run(self, *, path: str, **_kwargs) -> ToolOutput:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            line_count = content.count("\n") + 1
            return ToolOutput(
                status="success",
                summary=f"File '{path}' read successfully ({line_count} lines).",
                facts=[f"File '{path}' contains {line_count} lines of content."],
                data={"path": path, "content": content, "lines": line_count},
            )
        except FileNotFoundError:
            return ToolOutput(status="error", error=f"File '{path}' not found.")
        except Exception as e:
            return ToolOutput(status="error", error=f"Error reading '{path}': {e}")
