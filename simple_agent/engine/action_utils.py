from __future__ import annotations

from typing import Any


def _batch_items(action: Any) -> list[Any]:
    items = getattr(action, "actions", None)
    if items:
        return list(items)
    legacy = (getattr(action, "args", {}) or {}).get("actions", [])
    return list(legacy)


def _item_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def action_tool_name(action: Any) -> str:
    if getattr(action, "type", "") == "tool_batch":
        return "tool_batch"
    return str(getattr(action, "tool", "") or "")


def action_display_args(action: Any) -> dict:
    if getattr(action, "type", "") == "tool_batch":
        return {
            "actions": [
                {
                    "tool": _item_value(item, "tool", ""),
                    "args": _item_value(item, "args", {}) or {},
                    "depends_on": _item_value(item, "depends_on", []) or [],
                }
                for item in _batch_items(action)
            ]
        }
    return dict(getattr(action, "args", {}) or {})


def batch_action_targets(action: Any) -> list[str]:
    if getattr(action, "type", "") != "tool_batch":
        return []
    targets: list[str] = []
    for item in _batch_items(action):
        args = _item_value(item, "args", {}) or {}
        target = args.get("path") or args.get("root") or args.get("pattern")
        if target:
            targets.append(str(target))
    return targets


def action_intent_line(action: Any, *, step: int, max_steps: int) -> str:
    action_type = getattr(action, "type", "")
    reason = str(getattr(action, "reason", "") or "").strip()

    if action_type == "tool_call":
        tool = action_tool_name(action)
        args = action_display_args(action)
        target = args.get("path") or args.get("command") or args.get("root") or args.get("pattern")
        suffix = f" -> {target}" if target else ""
        base = f"[step {step}/{max_steps}] tool_call: {tool}{suffix}"
    elif action_type == "tool_batch":
        actions = action_display_args(action).get("actions", [])
        tools = ", ".join(item.get("tool", "?") for item in actions[:5])
        if len(actions) > 5:
            tools += f", +{len(actions) - 5} more"
        base = f"[step {step}/{max_steps}] tool_batch: {len(actions)} action(s) [{tools}]"
    else:
        base = f"[step {step}/{max_steps}] {action_type}"

    if reason:
        return f"{base}\n  intent: {reason}"
    return base
