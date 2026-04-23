from __future__ import annotations

import time

from simple_agent.context.artifact_state import ArtifactState
from simple_agent.context.context_layers import PromptContext
from simple_agent.engine.query_state import QueryState
from simple_agent.memory.memory_service import MemoryService
from simple_agent.sessions.schemas import SessionState, TurnState
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("context_service")

_SNAPSHOT_BUDGET = 2
_SNAPSHOT_MAX_CHARS = 1500
_SHELL_MAX_STDOUT = 1000
_SHELL_MAX_STDERR = 800


class ContextService:
    def __init__(self, memory_service: MemoryService, config: dict | None = None) -> None:
        self._memory = memory_service
        self._config = config or {}
        self._artifact_state = ArtifactState()
        self._ledger: dict[str, dict[str, list[dict]]] = {}

    @property
    def artifact_state(self) -> ArtifactState:
        return self._artifact_state

    async def append_message_event(
        self,
        session_id: str,
        role: str,
        content: str,
        turn_id: str | None = None,
    ) -> None:
        self._bucket(session_id)["messages"].append({
            "role": role,
            "content": content,
            "turn_id": turn_id,
            "timestamp": time.time(),
        })

    async def append_step_event(
        self,
        session_id: str,
        turn_id: str,
        step_id: int,
        payload: dict,
    ) -> None:
        self._bucket(session_id)["steps"].append({
            "step_id": step_id,
            "turn_id": turn_id,
            "payload": dict(payload),
            "timestamp": time.time(),
        })

    async def append_artifact_event(self, session_id: str, payload: dict) -> None:
        event = dict(payload)
        event.setdefault("timestamp", time.time())
        self._bucket(session_id)["artifacts"].append(event)

    async def get_recent_steps(self, session_id: str, limit: int = 20) -> list[dict]:
        return self._bucket(session_id)["steps"][-limit:]

    async def get_raw_segment(self, session_id: str, start_step: int, end_step: int) -> list[dict]:
        bucket = self._bucket(session_id)
        messages = [dict(item, kind="message") for item in bucket["messages"]]
        steps = [
            dict(item, kind="step")
            for item in bucket["steps"]
            if start_step <= item.get("step_id", 0) <= end_step
        ]
        artifacts = [
            dict(item, kind="artifact")
            for item in bucket["artifacts"]
            if start_step <= item.get("step_id", item.get("step", 0)) <= end_step
        ]
        return messages + steps + artifacts

    def _bucket(self, session_id: str) -> dict[str, list[dict]]:
        if session_id not in self._ledger:
            self._ledger[session_id] = {
                "messages": [],
                "steps": [],
                "artifacts": [],
            }
        return self._ledger[session_id]

    async def update_artifacts_from_tool(
        self, session_id: str, tool_name: str, result_dict: dict, step: int,
    ) -> None:
        ok = result_dict.get("ok", False)
        if not ok:
            await self.append_artifact_event(session_id, {
                "kind": "tool_result",
                "tool_name": tool_name,
                "step_id": step,
                "ok": False,
                "summary": result_dict.get("summary", ""),
                "error": result_dict.get("error"),
            })
            return

        data = result_dict.get("data", {})
        artifact_event = {
            "kind": "tool_result",
            "tool_name": tool_name,
            "step_id": step,
            "ok": True,
            "summary": result_dict.get("summary", ""),
        }

        if tool_name == "read_file":
            path = data.get("path", "")
            content = data.get("content", "")
            if path and content:
                self._artifact_state.update_from_read(path, content, step)
                artifact_event.update({
                    "kind": "read_snapshot",
                    "path": path,
                    "preview": content[:500],
                })

        elif tool_name == "write_file":
            path = data.get("path", "")
            operation = data.get("operation", "updated")
            if path:
                self._artifact_state.update_from_write(path, operation, step)
                artifact_event.update({
                    "kind": "write_guarantee",
                    "path": path,
                    "operation": operation,
                })

        elif tool_name == "bash":
            command = data.get("command", "")
            exit_code = data.get("exit_code", -1)
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            self._artifact_state.update_from_bash(command, exit_code, stdout, stderr)
            artifact_event.update({
                "kind": "shell_result",
                "command": command,
                "exit_code": exit_code,
                "stdout_preview": stdout[:500],
                "stderr_preview": stderr[:500],
            })

        await self.append_artifact_event(session_id, artifact_event)

    async def build_context(
        self, session: SessionState, turn: TurnState, state: QueryState,
    ) -> PromptContext:
        objective = self._build_objective_block(session, state)
        execution_state = self._build_execution_state(session, state)
        artifact_snapshot = self._build_artifact_snapshot()
        next_decision = self._build_next_decision_point(state)
        prompt_memory_block = await self._memory.build_prompt_memory(
            session.session_id,
            current_step=state.step_count,
        )

        return PromptContext(
            objective_block=objective,
            execution_state=execution_state,
            artifact_snapshot=artifact_snapshot,
            next_decision_point=next_decision,
            prompt_memory_block=prompt_memory_block,
        )

    def _build_objective_block(self, session: SessionState, state: QueryState) -> str:
        parts = [f"User objective:\n- {state.user_message}"]

        plan = state.current_plan
        if plan:
            overview = plan.get("overview") or plan.get("summary") or plan.get("goal", "")
            deliverables = plan.get("deliverables", [])
            verification_targets = plan.get("verification_targets", [])

            if overview:
                parts.append(f"\nPlan overview: {overview}")
            if deliverables:
                parts.append("Working assumptions:")
                for d in deliverables:
                    parts.append(f"- Deliverable: {d}")
            if verification_targets:
                for v in verification_targets:
                    parts.append(f"- Verification target: {v}")
        else:
            parts.append("\nWorking assumptions:")
            parts.append("- (No explicit plan. Deliverables inferred from user request.)")

        return "\n".join(parts)

    def _build_execution_state(self, session: SessionState, state: QueryState) -> str:
        lines = [
            f"mode={state.mode}",
            f"step={state.step_count}/{state.max_steps}",
        ]

        plan = state.current_plan
        if plan:
            steps = plan.get("steps", [])
            status_counts: dict[str, int] = {}
            for s in steps:
                st = s.get("status", "pending")
                status_counts[st] = status_counts.get(st, 0) + 1
            done = status_counts.get("done", 0) + status_counts.get("candidate_done", 0)
            total = len(steps)
            lines.append(f"plan_progress={done}/{total} steps advanced")

            # Show current pending step
            for s in steps:
                if s.get("status") == "pending":
                    action_type = s.get("action_type", "")
                    title = s.get("title", "")
                    criteria = s.get("completion_criteria", [])
                    lines.append(f"current_step={s.get('step_id', '?')}: [{action_type}] {title}")
                    if criteria:
                        for c in criteria[:2]:
                            lines.append(f"  completion: {c}")
                    break

            # Show blocked steps
            for s in steps:
                if s.get("status") == "blocked":
                    lines.append(f"blocked_step={s.get('step_id', '?')}: {s.get('title', '')} — consider replanning")

        if state.last_tool_result:
            tool = state.last_tool_result.get("tool_name", "?")
            ok = state.last_tool_result.get("ok", False)
            status = state.last_tool_result.get("status", "")
            lines.append(f"last_tool={tool}({status}, {'ok' if ok else 'failed'})")

        if session.active_turn_id:
            lines.append(f"active_turn={session.active_turn_id}")

        return "\n".join(lines)

    def _build_artifact_snapshot(self) -> str:
        parts: list[str] = []

        # File snapshots (budget-limited)
        snapshots = self._artifact_state.project_snapshots(
            budget=_SNAPSHOT_BUDGET,
            max_chars=_SNAPSHOT_MAX_CHARS,
        )
        if snapshots:
            parts.append("File snapshots:")
            parts.append(snapshots)

        # Write guarantees
        guarantees = self._artifact_state.project_write_guarantees()
        if guarantees:
            parts.append("Write guarantees:")
            parts.append(guarantees)

        # Latest shell result
        shell = self._artifact_state.project_latest_shell(
            max_stdout=_SHELL_MAX_STDOUT,
            max_stderr=_SHELL_MAX_STDERR,
        )
        if shell:
            parts.append("Latest shell result:")
            parts.append(shell)

        return "\n\n".join(parts) if parts else ""

    def _build_next_decision_point(self, state: QueryState) -> str:
        plan = state.current_plan
        if not plan:
            return (
                "Next decision: Decide the best action to advance the task.\n"
                "Prefer run/verify/finish over another write unless a concrete gap is identified."
            )

        steps = plan.get("steps", [])
        for s in steps:
            status = s.get("status", "")
            if status == "blocked":
                return (
                    f"Step {s.get('step_id', '?')} is blocked — "
                    "multiple successful actions have not satisfied completion criteria.\n"
                    "Consider replanning."
                )
            if status == "pending":
                action_type = s.get("action_type", "")
                title = s.get("title", "")
                hint = f"Next checkpoint: [{action_type}] {title}.\n"
                hint += "First decide whether the current state already satisfies its completion criteria.\n"
                if action_type == "modify":
                    hint += "Prefer run/verify before another write."
                elif action_type in ("run", "verify"):
                    hint += "Run/verify before attempting another modification."
                else:
                    hint += "Prefer inspect/run/verify before another write unless a specific gap is identified."
                return hint

        return "All plan steps have been addressed. Prefer verify or finish."
