from __future__ import annotations

from simple_agent.tools.core.types import ToolObservation


# Strong write-enabling evidence types
_FAILED_BASH = "failed_bash"
_FAILED_VERIFY = "failed_verify"
_NEW_READ_GAP = "new_read_gap"
_NEW_USER_INPUT = "new_user_input"


def _classify_last_evidence(last_result: dict | None) -> str | None:
    """Classify what kind of evidence the last tool result provides."""
    if not last_result:
        return None

    tool_name = last_result.get("tool_name", "")
    ok = last_result.get("ok", False)

    # Failed bash is strong evidence for another write
    if tool_name == "bash" and not ok:
        return _FAILED_BASH

    # Failed verification is strong evidence
    if tool_name == "verify" and not ok:
        return _FAILED_VERIFY

    # A read that revealed something (not just after a write to the same file)
    if tool_name == "read_file" and ok:
        return _NEW_READ_GAP

    return None


async def check_write_without_evidence(
    tool_name: str,
    args: dict,
    last_tool_result: dict | None,
) -> ToolObservation | None:
    """Block a new write if there's no strong evidence since the last write."""
    if tool_name != "write_file":
        return None
    target = args.get("path")
    if not target or not last_tool_result:
        return None

    # Only block if the last result was also a successful write to the same file
    if (last_tool_result.get("tool_name") == "write_file"
            and last_tool_result.get("ok")
            and last_tool_result.get("changed_paths") == [target]):
        # Check if there's strong evidence between the two writes
        # Since we only see last_tool_result, if it IS the previous write,
        # there's no intervening evidence
        return ToolObservation(
            ok=False,
            status="context_required",
            summary=f"Write to '{target}' blocked: no new evidence since last successful write.",
            error=(
                "Another write requires strong evidence: "
                "a failed test, an incomplete verification, a new user instruction, "
                "or a read that revealed a concrete gap."
            ),
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
            error=f"File '{target}' was just written successfully. Re-reading is unnecessary — trust the write guarantee.",
        )
    return None
