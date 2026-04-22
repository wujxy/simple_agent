from __future__ import annotations

import os

from simple_agent.schemas import ToolOutput
from simple_agent.tools.base import BaseTool


class ListDirTool(BaseTool):
    name = "list_dir"
    description = "List files and directories in a given path"
    args_schema = {"path": "string - directory path"}

    async def run(self, *, path: str, **_kwargs) -> ToolOutput:
        try:
            entries = sorted(os.listdir(path))
            if not entries:
                return ToolOutput(
                    status="success",
                    summary=f"Directory '{path}' is empty.",
                    facts=[f"Directory '{path}' contains no entries."],
                    data={"path": path, "entries": []},
                )
            preview = ", ".join(entries[:10])
            return ToolOutput(
                status="success",
                summary=f"Directory '{path}' listed successfully ({len(entries)} entries).",
                facts=[f"Directory '{path}' contains {len(entries)} entries: {preview}."],
                data={"path": path, "entries": entries},
            )
        except FileNotFoundError:
            return ToolOutput(status="error", error=f"Directory '{path}' not found.")
        except Exception as e:
            return ToolOutput(status="error", error=f"Error listing '{path}': {e}")
