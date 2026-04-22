from __future__ import annotations

import difflib
import os

from simple_agent.schemas import ToolOutput
from simple_agent.tools.base import BaseTool


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a text file"
    args_schema = {"path": "string - file path", "content": "string - content to write"}

    async def run(self, *, path: str, content: str, **_kwargs) -> ToolOutput:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

            is_new = not os.path.exists(path)
            old_lines: list[str] = []
            if not is_new:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        old_lines = f.read().splitlines(keepends=True)
                except Exception:
                    is_new = True

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            new_lines = content.splitlines(keepends=True)
            op = "created" if is_new else "updated"

            diff_lines = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{path}", tofile=f"b/{path}",
                n=0,
            ))
            added = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
            removed = sum(1 for l in diff_lines if l.startswith('-') and not l.startswith('---'))

            return ToolOutput(
                status="success",
                summary=f"File '{path}' was {op} successfully. "
                        f"The file now exactly matches the content you supplied "
                        f"({added} lines added, {removed} removed).",
                facts=[f"{path} now exactly matches the content you supplied in this call."],
                data={
                    "path": path, "operation": op,
                    "lines_written": len(new_lines),
                    "lines_added": added, "lines_removed": removed,
                },
            )
        except Exception as e:
            return ToolOutput(status="error", error=f"Error writing to '{path}': {e}")
