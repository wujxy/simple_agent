from __future__ import annotations

from simple_agent.tools.core.types import ToolObservation


_WRITE_TOOLS = {"write_file", "edit_file", "multi_edit"}


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
    if tool_name not in _WRITE_TOOLS:
        return None
    target = args.get("path")
    if not target or not last_tool_result:
        return None

    # Only block if the last result was also a successful write to the same file
    if (last_tool_result.get("tool_name") in _WRITE_TOOLS
            and last_tool_result.get("ok")
            and target in last_tool_result.get("changed_paths", [])):
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
    last_tool = last_tool_result.get("tool_name")
    if (last_tool in _WRITE_TOOLS
            and last_tool_result.get("ok")
            and target in last_tool_result.get("changed_paths", [])):
        return ToolObservation(
            ok=False,
            status="context_required",
            summary=f"Read of '{target}' blocked: file was just updated successfully.",
            error=(
                f"File '{target}' was just updated successfully by {last_tool}. "
                "Re-reading is unnecessary; use run/verify/finish unless you have a concrete new gap."
            ),
        )
    return None


async def check_repeated_read(
    tool_name: str,
    args: dict,
    last_tool_result: dict | None,
) -> ToolObservation | None:
    """Block immediately repeated full reads of the same file."""
    if tool_name != "read_file":
        return None
    target = args.get("path")
    if not target or not last_tool_result:
        return None
    if last_tool_result.get("tool_name") != "read_file" or not last_tool_result.get("ok"):
        return None

    data = last_tool_result.get("data", {})
    if not isinstance(data, dict) or data.get("path") != target:
        return None

    requested_start = int(args.get("start_line") or 1)
    requested_max = args.get("max_lines")
    previous_truncated = bool(data.get("truncated", False))

    if requested_start == 1 and requested_max is None and not previous_truncated:
        return ToolObservation(
            ok=False,
            status="context_required",
            summary=f"Repeated read of '{target}' blocked: file was already fully read.",
            error=(
                f"File '{target}' was already fully read in the previous step. "
                "Use the working set/memory and proceed to run, verify, or finish."
            ),
        )
    return None
