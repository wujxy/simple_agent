from __future__ import annotations

from simple_agent.runtime.event_types import (
    RUNTIME_ACTION_PARSED,
    RUNTIME_APPROVAL_REQUIRED,
    RUNTIME_CONTEXT_BUDGET_UPDATED,
    RUNTIME_LLM_COMPLETED,
    RUNTIME_STEP_COMPLETED,
    RUNTIME_TOOL_COMPLETED,
    RUNTIME_TOOL_PROGRESS,
    RUNTIME_TOOL_STARTED,
    RUNTIME_TURN_COMPLETED,
    RUNTIME_TURN_STARTED,
)


def _short(value: object, limit: int = 120) -> str:
    text = str(value or "")
    text = text.replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _target(payload: dict) -> str:
    args = payload.get("args") or {}
    return str(
        payload.get("target")
        or args.get("path")
        or args.get("command")
        or args.get("root")
        or args.get("pattern")
        or ""
    )


class CliEventRenderer:
    """Human-readable renderer for runtime events."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose

    def __call__(self, event) -> None:
        text = self.render(event)
        if text:
            print(text)

    def render(self, event) -> str:
        payload = event.payload or {}
        event_type = event.type

        if event_type == RUNTIME_TURN_STARTED:
            run_mode = payload.get("run_mode", "normal")
            return (
                f"\nturn started: {event.turn_id} [{run_mode}]\n"
                f"task: {_short(payload.get('user_message'), 180)}\n"
                f"max steps: {payload.get('max_steps')}"
            )

        if event_type == RUNTIME_ACTION_PARSED:
            return self._render_action(payload)

        if event_type == RUNTIME_CONTEXT_BUDGET_UPDATED:
            return self._render_budget(payload)

        if event_type == RUNTIME_LLM_COMPLETED:
            prompt_chars = int(payload.get("prompt_chars") or 0)
            response_chars = int(payload.get("response_chars") or 0)
            tokens = int(payload.get("prompt_estimated_tokens") or 0)
            return f"llm: prompt {prompt_chars} chars (~{tokens} tokens), response {response_chars} chars"

        if event_type == RUNTIME_TOOL_STARTED:
            tool = payload.get("tool_name", "?")
            target = _target(payload)
            suffix = f" -> {_short(target, 100)}" if target else ""
            return f"tool: {tool} started{suffix}"

        if event_type == RUNTIME_APPROVAL_REQUIRED:
            tool = payload.get("tool_name", "?")
            run_mode = payload.get("run_mode", "normal")
            target = _target(payload)
            suffix = f" -> {_short(target, 100)}" if target else ""
            intent = payload.get("intent") or ""
            reason = payload.get("reason") or payload.get("message") or ""
            lines = [f"approval required [{run_mode}]: {tool}{suffix}"]
            if intent:
                lines.append(f"  intent: {_short(intent, 180)}")
            if reason:
                lines.append(f"  reason: {_short(reason, 180)}")
            return "\n".join(lines)

        if event_type == RUNTIME_TOOL_PROGRESS:
            label = payload.get("label") or payload.get("tool_name") or "tool_batch"
            return (
                f"{label}: running {payload.get('running', 0)}, "
                f"completed {payload.get('completed', 0)}, "
                f"failed {payload.get('failed', 0)}, skipped {payload.get('skipped', 0)}"
            )

        if event_type == RUNTIME_TOOL_COMPLETED:
            return self._render_tool_completed(payload)

        if event_type == RUNTIME_STEP_COMPLETED:
            return (
                f"step completed: {payload.get('transition_type')} "
                f"({payload.get('reason')})"
            )

        if event_type == RUNTIME_TURN_COMPLETED:
            run_mode = payload.get("run_mode", "normal")
            return (
                f"\nturn completed [{run_mode}]: {payload.get('status')}\n"
                f"{payload.get('message')}"
            )

        return ""

    def _render_action(self, payload: dict) -> str:
        step = payload.get("step", "?")
        max_steps = payload.get("max_steps", "?")
        action_type = payload.get("action_type", "")
        intent = payload.get("reason") or ""
        run_mode = payload.get("run_mode", "normal")

        if action_type == "tool_call":
            tool = payload.get("tool_name", "?")
            target = _target(payload)
            suffix = f" -> {_short(target, 100)}" if target else ""
            head = f"[step {step}/{max_steps}][{run_mode}] tool_call: {tool}{suffix}"
        elif action_type == "tool_batch":
            count = payload.get("batch_count", 0)
            tools = ", ".join(payload.get("batch_tools", [])[:5])
            if count and count > 5:
                tools += f", +{count - 5} more"
            head = f"[step {step}/{max_steps}][{run_mode}] tool_batch: {count} action(s) [{tools}]"
        else:
            head = f"[step {step}/{max_steps}][{run_mode}] {action_type}"

        if intent:
            return f"{head}\n  intent: {_short(intent, 220)}"
        return head

    def _render_budget(self, payload: dict) -> str:
        prompt = payload.get("prompt", {})
        memory = payload.get("memory", {})
        working_set = payload.get("working_set", {})
        artifact = payload.get("artifact", {})
        lines = [
            (
                "context: "
                f"{prompt.get('total_chars', 0)} chars "
                f"(~{prompt.get('estimated_tokens', 0)} tokens), "
                f"{prompt.get('token_percent', 0)}% of {prompt.get('token_budget', 0)} tokens"
            ),
            (
                "memory: "
                f"{memory.get('current_chars', 0)} / {memory.get('char_budget', 0)} chars, "
                f"compact at {memory.get('threshold_percent', 0)}%, "
                f"{memory.get('remaining_chars', 0)} chars remaining"
            ),
            (
                "working set: "
                f"{working_set.get('files_tracked', 0)} files tracked, "
                f"{working_set.get('files_projected', 0)} projected, "
                f"{working_set.get('modified_paths', 0)} modified, "
                f"{working_set.get('grep_hits', 0)} grep hits; "
                f"artifacts projected {artifact.get('projected_snapshots', 0)}"
            ),
        ]
        return "\n".join(lines)

    def _render_tool_completed(self, payload: dict) -> str:
        tool = payload.get("tool_name", "?")
        ok = "ok" if payload.get("ok") else "failed"
        status = payload.get("status") or ""
        lines = [f"tool: {tool} completed {ok} ({status})"]
        if payload.get("summary"):
            lines.append(f"  summary: {_short(payload.get('summary'), 180)}")
        for fact in (payload.get("facts") or [])[:2]:
            lines.append(f"  fact: {_short(fact, 180)}")
        if payload.get("changed_paths"):
            lines.append(f"  changed: {', '.join(payload.get('changed_paths')[:5])}")
        if payload.get("files_read"):
            lines.append(f"  files read: {', '.join(payload.get('files_read')[:8])}")
        if payload.get("truncated_files"):
            lines.append(f"  truncated: {', '.join(payload.get('truncated_files')[:8])}")
        if payload.get("error"):
            lines.append(f"  error: {_short(payload.get('error'), 220)}")
        for error in (payload.get("errors") or [])[:3]:
            lines.append(f"  error: {_short(error, 220)}")
        return "\n".join(lines)
