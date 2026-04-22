from __future__ import annotations

import os

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolObservation
from simple_agent.tools.list_dir.schemas import ListDirInput
from simple_agent.tools.list_dir.spec import ListDirSpec


class ListDirTool(BaseTool):
    spec = ListDirSpec
    input_model = ListDirInput

    async def run(self, tool_input: ListDirInput, ctx: dict | None = None) -> ToolObservation:
        path = tool_input.path

        try:
            entries = sorted(os.listdir(path))
        except FileNotFoundError:
            return ToolObservation(ok=False, status="error", error=f"Directory '{path}' not found.")
        except NotADirectoryError:
            return ToolObservation(ok=False, status="error", error=f"'{path}' is not a directory.")
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Error listing '{path}': {e}")

        if not entries:
            return ToolObservation(
                ok=True,
                status="success",
                summary=f"Directory '{path}' is empty.",
                facts=[f"Directory '{path}' contains no entries."],
                data={"path": path, "entries": []},
            )

        preview = ", ".join(entries[:10])
        return ToolObservation(
            ok=True,
            status="success",
            summary=f"Directory '{path}' listed ({len(entries)} entries).",
            facts=[f"Directory '{path}' contains {len(entries)} entries: {preview}."],
            data={"path": path, "entries": entries},
        )
