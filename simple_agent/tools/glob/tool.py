from __future__ import annotations

from pathlib import Path

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolObservation
from simple_agent.tools.glob.schemas import GlobInput
from simple_agent.tools.glob.spec import GlobSpec


class GlobTool(BaseTool):
    spec = GlobSpec
    input_model = GlobInput

    async def run(self, tool_input: GlobInput, ctx: dict | None = None) -> ToolObservation:
        root = Path(tool_input.root)
        try:
            matches = sorted(str(p) for p in root.glob(tool_input.pattern))
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Glob failed: {e}")

        truncated = len(matches) > tool_input.max_results
        shown = matches[:tool_input.max_results]
        preview = ", ".join(shown[:10])
        return ToolObservation(
            ok=True,
            status="success",
            summary=f"Glob matched {len(matches)} path(s); returning {len(shown)}.",
            facts=[f"Glob '{tool_input.pattern}' under '{tool_input.root}' matched {len(matches)} path(s): {preview}."],
            data={
                "root": tool_input.root,
                "pattern": tool_input.pattern,
                "matches": shown,
                "match_count": len(matches),
                "truncated": truncated,
            },
            memory={
                "summary": f"Glob '{tool_input.pattern}' found {len(matches)} path(s).",
                "facts": [f"Glob result preview: {preview}." if preview else "Glob found no paths."],
            },
            artifacts={"kind": "glob_matches", "matches": shown, "match_count": len(matches)},
            display={"matches": shown[:20], "match_count": len(matches), "truncated": truncated},
        )
