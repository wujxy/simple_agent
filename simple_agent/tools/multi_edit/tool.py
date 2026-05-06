from __future__ import annotations

from pathlib import Path

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolObservation
from simple_agent.tools.multi_edit.schemas import MultiEditInput
from simple_agent.tools.multi_edit.spec import MultiEditSpec


class MultiEditTool(BaseTool):
    spec = MultiEditSpec
    input_model = MultiEditInput

    async def run(self, tool_input: MultiEditInput, ctx: dict | None = None) -> ToolObservation:
        path = Path(tool_input.path)
        try:
            original = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolObservation(ok=False, status="error", error=f"File '{tool_input.path}' not found.")
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Error reading '{tool_input.path}': {e}")

        content = original
        replacements = 0
        for idx, edit in enumerate(tool_input.edits, start=1):
            count = content.count(edit.old_text)
            if count == 0:
                return ToolObservation(
                    ok=False,
                    status="error",
                    error=f"Edit {idx}: old_text was not found exactly. No write performed.",
                    retryable=True,
                    memory={
                        "summary": f"multi_edit failed for '{tool_input.path}' at edit {idx}.",
                        "errors": [f"Edit {idx}: old_text not found."],
                    },
                )
            if count > 1 and not edit.replace_all:
                return ToolObservation(
                    ok=False,
                    status="error",
                    error=f"Edit {idx}: old_text matched multiple locations. No write performed.",
                    retryable=True,
                    memory={
                        "summary": f"multi_edit failed for '{tool_input.path}' at edit {idx}.",
                        "errors": [f"Edit {idx}: multiple matches."],
                    },
                )
            n = count if edit.replace_all else 1
            content = content.replace(edit.old_text, edit.new_text, n)
            replacements += n

        if content == original:
            return ToolObservation(
                ok=True,
                status="noop",
                summary=f"No changes needed for '{tool_input.path}'.",
                data={"path": tool_input.path, "edits_applied": 0, "replacements": 0},
                memory={"summary": f"multi_edit noop for '{tool_input.path}'."},
            )

        try:
            path.write_text(content, encoding="utf-8")
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Error writing '{tool_input.path}': {e}")

        return ToolObservation(
            ok=True,
            status="success",
            summary=f"Applied {len(tool_input.edits)} edit(s) to '{tool_input.path}' ({replacements} replacement(s)).",
            facts=[f"{tool_input.path}: multi_edit applied {replacements} replacement(s)."],
            data={
                "path": tool_input.path,
                "edits_applied": len(tool_input.edits),
                "replacements": replacements,
            },
            changed_paths=[tool_input.path],
            memory={
                "summary": f"multi_edit updated '{tool_input.path}' with {replacements} replacement(s).",
                "facts": [f"{tool_input.path}: multi_edit applied successfully."],
                "changed_paths": [tool_input.path],
            },
            artifacts={"kind": "file_edit", "path": tool_input.path, "replacements": replacements},
            display={"path": tool_input.path, "replacements": replacements},
        )
