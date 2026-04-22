from __future__ import annotations

from simple_agent.tools.core.types import ToolObservation


async def check_write_without_evidence(
    tool_name: str,
    args: dict,
    last_tool_result: dict | None,
) -> ToolObservation | None:
    """Block a new write to the same file if there's no new evidence since the last write."""
    if tool_name != "write_file":
        return None
    target = args.get("path")
    if not target or not last_tool_result:
        return None
    if (last_tool_result.get("tool_name") == "write_file"
            and last_tool_result.get("ok")
            and last_tool_result.get("changed_paths") == [target]):
        return ToolObservation(
            ok=False,
            status="context_required",
            summary=f"Write to '{target}' blocked: no new evidence since last successful write.",
            error="A new write requires new evidence (a failed test, new user input, or verification gap).",
        )
    return None


async def check_read_after_write(
    tool_name: str,
    args: dict,
    last_tool_result: dict | None,
) -> ToolObservation | None:
    """Block re-reading a file that was just written successfully."""
    if tool_name != "read_file":
        return None
    target = args.get("path")
    if not target or not last_tool_result:
        return None
    if (last_tool_result.get("tool_name") == "write_file"
            and last_tool_result.get("ok")
            and target in last_tool_result.get("changed_paths", [])):
        return ToolObservation(
            ok=False,
            status="context_required",
            summary=f"Read of '{target}' blocked: file was just written. You already know its content.",
            error=f"File '{target}' was just written successfully. Re-reading is unnecessary unless you need to verify an external change.",
        )
    return None
