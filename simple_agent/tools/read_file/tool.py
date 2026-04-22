from __future__ import annotations

import hashlib

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolObservation
from simple_agent.tools.read_file.schemas import ReadFileInput
from simple_agent.tools.read_file.spec import ReadFileSpec


class ReadFileTool(BaseTool):
    spec = ReadFileSpec
    input_model = ReadFileInput

    async def run(self, tool_input: ReadFileInput, ctx: dict | None = None) -> ToolObservation:
        path = tool_input.path
        start_line = tool_input.start_line
        max_lines = tool_input.max_lines

        try:
            with open(path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
        except FileNotFoundError:
            return ToolObservation(ok=False, status="error", error=f"File '{path}' not found.")
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Error reading '{path}': {e}")

        total_lines = len(all_lines)
        content_hash = hashlib.md5("".join(all_lines).encode()).hexdigest()

        # Check for unchanged (same range, same hash) via ctx
        if ctx:
            read_cache = ctx.get("read_cache", {})
            cache_key = f"{path}:{start_line}:{max_lines}"
            cached = read_cache.get(cache_key)
            if cached and cached.get("hash") == content_hash:
                return ToolObservation(
                    ok=True,
                    status="unchanged",
                    summary=f"File '{path}' unchanged since last read.",
                    facts=[f"File '{path}' has not changed since last read ({total_lines} lines)."],
                    data={"path": path, "total_lines": total_lines},
                )

        # Slice content
        sliced = all_lines[start_line - 1:]
        if max_lines is not None:
            sliced = sliced[:max_lines]
        truncated = max_lines is not None and (start_line - 1 + max_lines) < total_lines
        content = "".join(sliced)

        # Update cache
        if ctx is not None:
            if "read_cache" not in ctx:
                ctx["read_cache"] = {}
            ctx["read_cache"][f"{path}:{start_line}:{max_lines}"] = {
                "hash": content_hash,
                "total_lines": total_lines,
            }

        lines_read = len(sliced)
        return ToolObservation(
            ok=True,
            status="success",
            summary=f"Read '{path}' ({lines_read} lines, total {total_lines}).",
            facts=[f"File '{path}' has {total_lines} lines."],
            data={
                "path": path,
                "content": content,
                "total_lines": total_lines,
                "lines_read": lines_read,
                "truncated": truncated,
            },
        )
