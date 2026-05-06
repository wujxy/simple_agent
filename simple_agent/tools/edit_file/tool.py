from __future__ import annotations

from pathlib import Path

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolObservation
from simple_agent.tools.edit_file.schemas import EditFileInput
from simple_agent.tools.edit_file.spec import EditFileSpec


class EditFileTool(BaseTool):
    spec = EditFileSpec
    input_model = EditFileInput

    async def run(self, tool_input: EditFileInput, ctx: dict | None = None) -> ToolObservation:
        path = Path(tool_input.path)
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolObservation(ok=False, status="error", error=f"File '{tool_input.path}' not found.")
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Error reading '{tool_input.path}': {e}")

        count = content.count(tool_input.old_text)
        if count == 0:
            return ToolObservation(
                ok=False,
                status="error",
                summary=f"No exact match found in '{tool_input.path}'.",
                error="old_text was not found exactly.",
                retryable=True,
                memory={
                    "summary": f"Edit failed for '{tool_input.path}': old_text not found.",
                    "errors": ["old_text was not found exactly."],
                },
            )
        if count > 1 and not tool_input.replace_all:
            return ToolObservation(
                ok=False,
                status="error",
                summary=f"Multiple matches found in '{tool_input.path}'.",
                error="old_text matched multiple locations; set replace_all=true or provide more context.",
                retryable=True,
                memory={
                    "summary": f"Edit failed for '{tool_input.path}': multiple matches found.",
                    "errors": ["old_text matched multiple locations."],
                },
            )

        replacements = count if tool_input.replace_all else 1
        new_content = content.replace(tool_input.old_text, tool_input.new_text, replacements)
        try:
            path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Error writing '{tool_input.path}': {e}")

        lines_added = tool_input.new_text.count("\n") - tool_input.old_text.count("\n")
        lines_removed = max(0, -lines_added)
        lines_added = max(0, lines_added)
        return ToolObservation(
            ok=True,
            status="success",
            summary=f"Edited '{tool_input.path}' ({replacements} replacement(s)).",
            facts=[f"{tool_input.path}: applied {replacements} exact replacement(s)."],
            data={
                "path": tool_input.path,
                "replacements": replacements,
                "lines_added": lines_added,
                "lines_removed": lines_removed,
            },
            changed_paths=[tool_input.path],
            memory={
                "summary": f"Edited '{tool_input.path}' with {replacements} exact replacement(s).",
                "facts": [f"{tool_input.path}: edit applied successfully."],
                "changed_paths": [tool_input.path],
            },
            artifacts={
                "kind": "file_edit",
                "path": tool_input.path,
                "replacements": replacements,
                "lines_added": lines_added,
                "lines_removed": lines_removed,
            },
            display={"path": tool_input.path, "replacements": replacements},
        )
