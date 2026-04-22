from __future__ import annotations

import difflib
import os

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolObservation
from simple_agent.tools.write_file.schemas import WriteFileInput
from simple_agent.tools.write_file.spec import WriteFileSpec


class WriteFileTool(BaseTool):
    spec = WriteFileSpec
    input_model = WriteFileInput

    async def run(self, tool_input: WriteFileInput, ctx: dict | None = None) -> ToolObservation:
        path = tool_input.path
        content = tool_input.content

        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Cannot create parent dirs for '{path}': {e}")

        is_new = not os.path.exists(path)
        old_content = ""

        if not is_new:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old_content = f.read()
            except Exception:
                is_new = True

        # Noop detection: content already matches
        if not is_new and old_content == content:
            return ToolObservation(
                ok=True,
                status="noop",
                summary=f"File '{path}' already has identical content. No write performed.",
                facts=[f"File '{path}' content is identical to the requested write."],
                data={"path": path, "operation": "noop", "lines_written": content.count("\n") + 1},
            )

        old_lines = old_content.splitlines(keepends=True)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Error writing to '{path}': {e}")

        new_lines = content.splitlines(keepends=True)
        op = "created" if is_new else "updated"

        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}", tofile=f"b/{path}",
            n=0,
        ))
        added = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
        removed = sum(1 for l in diff_lines if l.startswith('-') and not l.startswith('---'))

        return ToolObservation(
            ok=True,
            status="success",
            summary=f"File '{path}' was {op} ({added} lines added, {removed} removed). "
                    f"The file now exactly matches the content you supplied.",
            facts=[f"{path} now exactly matches the content you supplied in this call."],
            data={
                "path": path,
                "operation": op,
                "lines_written": len(new_lines),
                "lines_added": added,
                "lines_removed": removed,
            },
            changed_paths=[path],
        )
