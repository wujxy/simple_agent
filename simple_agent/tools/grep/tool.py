from __future__ import annotations

from pathlib import Path

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolObservation
from simple_agent.tools.grep.schemas import GrepInput
from simple_agent.tools.grep.spec import GrepSpec


class GrepTool(BaseTool):
    spec = GrepSpec
    input_model = GrepInput

    async def run(self, tool_input: GrepInput, ctx: dict | None = None) -> ToolObservation:
        root = Path(tool_input.root)
        needle = tool_input.pattern if tool_input.case_sensitive else tool_input.pattern.lower()
        matches: list[dict] = []
        total = 0

        try:
            paths = sorted(p for p in root.glob(tool_input.include) if p.is_file())
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Grep failed: {e}")

        for path in paths:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
            for idx, line in enumerate(lines, start=1):
                haystack = line if tool_input.case_sensitive else line.lower()
                if needle in haystack:
                    total += 1
                    if len(matches) < tool_input.max_results:
                        matches.append({"path": str(path), "line_number": idx, "line": line[:500]})

        truncated = total > len(matches)
        preview = "; ".join(f"{m['path']}:{m['line_number']}" for m in matches[:10])
        return ToolObservation(
            ok=True,
            status="success",
            summary=f"Grep found {total} match(es); returning {len(matches)}.",
            facts=[f"Pattern '{tool_input.pattern}' matched {total} line(s): {preview}."],
            data={
                "pattern": tool_input.pattern,
                "root": tool_input.root,
                "include": tool_input.include,
                "matches": matches,
                "match_count": total,
                "truncated": truncated,
            },
            memory={
                "summary": f"Grep '{tool_input.pattern}' found {total} match(es).",
                "facts": [f"Grep hits: {preview}." if preview else "Grep found no matches."],
                "references": [
                    {"path": m["path"], "start_line": m["line_number"], "end_line": m["line_number"]}
                    for m in matches[:20]
                ],
            },
            artifacts={"kind": "grep_hits", "matches": matches, "match_count": total},
            display={"matches": matches[:20], "match_count": total, "truncated": truncated},
        )
