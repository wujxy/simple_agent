from __future__ import annotations

import time
from pathlib import Path

from simple_agent.context.artifact_state import ArtifactState
from simple_agent.context.context_layers import PromptContext
from simple_agent.context.working_set import WorkingSetState
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
        self._artifact_states: dict[str, ArtifactState] = {}
        self._working_sets: dict[str, WorkingSetState] = {}
        self._ledger: dict[str, dict[str, list[dict]]] = {}

    @property
    def artifact_state(self) -> ArtifactState:
        if not self._artifact_states:
            self._artifact_states["default"] = ArtifactState()
        return next(iter(self._artifact_states.values()))

    def _artifact_state_for(self, session_id: str) -> ArtifactState:
        if session_id not in self._artifact_states:
            self._artifact_states[session_id] = ArtifactState()
        return self._artifact_states[session_id]

    def _working_set_for(self, session_id: str) -> WorkingSetState:
        if session_id not in self._working_sets:
            self._working_sets[session_id] = WorkingSetState()
        return self._working_sets[session_id]

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
                self._artifact_state_for(session_id).update_from_read(path, content, step)
                artifacts = result_dict.get("artifacts", {})
                metadata = result_dict.get("metadata", {})
                start_line = int(artifacts.get("start_line") or metadata.get("start_line") or 1)
                end_line = int(artifacts.get("end_line") or metadata.get("end_line") or start_line)
                total_lines = int(data.get("total_lines") or metadata.get("total_lines") or end_line)
                self._working_set_for(session_id).update_from_read(
                    path=path,
                    content=content,
                    start_line=start_line,
                    end_line=end_line,
                    total_lines=total_lines,
                    truncated=bool(data.get("truncated", False)),
                    content_hash=str(metadata.get("content_hash", "")),
                    step=step,
                )
                artifact_event.update({
                    "kind": "read_snapshot",
                    "path": path,
                    "preview": content[:500],
                })

        elif tool_name == "write_file":
            path = data.get("path", "")
            operation = data.get("operation", "updated")
            if path:
                self._artifact_state_for(session_id).update_from_write(path, operation, step)
                self._working_set_for(session_id).update_from_write(path=path, step=step)
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
            self._artifact_state_for(session_id).update_from_bash(command, exit_code, stdout, stderr)
            self._working_set_for(session_id).update_from_bash(
                command=command, exit_code=exit_code, stderr=stderr, step=step,
            )
            artifact_event.update({
                "kind": "shell_result",
                "command": command,
                "exit_code": exit_code,
                "stdout_preview": stdout[:500],
                "stderr_preview": stderr[:500],
            })

        elif tool_name == "grep":
            hits = data.get("matches", [])
            self._working_set_for(session_id).update_from_grep(hits, step=step)
            artifact_event.update({
                "kind": "grep_hits",
                "match_count": len(hits),
            })

        elif tool_name in ("edit_file", "multi_edit"):
            for path in result_dict.get("changed_paths", []):
                self._artifact_state_for(session_id).update_from_write(path, "updated", step)
                self._working_set_for(session_id).update_from_write(path=path, step=step)

        await self.append_artifact_event(session_id, artifact_event)

    async def build_context(
        self, session: SessionState, turn: TurnState, state: QueryState,
    ) -> PromptContext:
        objective = self._build_objective_block(session, state)
        execution_state = self._build_execution_state(session, state)
        project_rules = self._build_project_rules_block(session)
        working_set = self._working_set_for(session.session_id).project()
        artifact_snapshot = self._build_artifact_snapshot(session.session_id)
        next_decision = self._build_next_decision_point(state)
        prompt_memory_block = await self._memory.build_prompt_memory(
            session.session_id,
            current_step=state.step_count,
        )

        return PromptContext(
            project_rules_block=project_rules,
            objective_block=objective,
            execution_state=execution_state,
            working_set_block=working_set,
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
            f"run_mode={state.run_mode}",
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

    def _build_project_rules_block(self, session: SessionState) -> str:
        roots: list[Path] = []
        if session.cwd:
            roots.append(Path(session.cwd))
        roots.append(Path.cwd())

        seen: set[Path] = set()
        parts: list[str] = []
        for root in roots:
            for name in ("CLAUDE.md", "project.md"):
                path = (root / name).resolve()
                if path in seen or not path.exists() or not path.is_file():
                    continue
                seen.add(path)
                try:
                    content = path.read_text(encoding="utf-8")
                except Exception:
                    continue
                if content.strip():
                    parts.append(f"[{path.name}]\n{content[:4000]}")
        return "\n\n".join(parts)

    def _build_artifact_snapshot(self, session_id: str) -> str:
        parts: list[str] = []
        artifact_state = self._artifact_state_for(session_id)

        # File snapshots (budget-limited)
        snapshots = artifact_state.project_snapshots(
            budget=_SNAPSHOT_BUDGET,
            max_chars=_SNAPSHOT_MAX_CHARS,
        )
        if snapshots:
            parts.append("File snapshots:")
            parts.append(snapshots)

        # Write guarantees
        guarantees = artifact_state.project_write_guarantees()
        if guarantees:
            parts.append("Write guarantees:")
            parts.append(guarantees)

        # Latest shell result
        shell = artifact_state.project_latest_shell(
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
            if state.last_tool_result and state.last_tool_result.get("ok"):
                tool = state.last_tool_result.get("tool_name", "")
                if tool in ("write_file", "edit_file", "multi_edit"):
                    return (
                        "Next decision: The last file update succeeded and is recorded in memory/artifacts.\n"
                        "Do not re-read the same file just to confirm the write. Prefer run, verify, or finish."
                    )
                if tool == "read_file":
                    return (
                        "Next decision: The last file read succeeded and its content is in the working set.\n"
                        "Do not repeat the same read. Use the evidence to act, verify, or finish."
                    )
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

    def runtime_snapshot(self, session_id: str, prompt_context: PromptContext | None = None) -> dict:
        working_set = self._working_set_for(session_id)
        artifact_state = self._artifact_state_for(session_id)
        active_files = [f for f in working_set.files.values() if not f.stale and f.content]
        active_files.sort(key=lambda f: f.last_updated_step, reverse=True)
        artifact_snapshots = [
            f for f in artifact_state.files.values()
            if f.exists and f.snapshot and not f.stale
        ]
        return {
            "working_set": {
                "files_tracked": len(working_set.files),
                "files_projected": min(len(active_files), 4),
                "modified_paths": len(working_set.modified_paths),
                "grep_hits": len(working_set.grep_hits),
                "recent_failures": len(working_set.recent_failures),
            },
            "artifact": {
                "active_files": len(artifact_state.get_active_files()),
                "projected_snapshots": min(len(artifact_snapshots), 2),
                "write_guarantees": len(artifact_state.write_guarantees),
                "shell_results": len(artifact_state.shell_results),
            },
            "projected_chars": {
                "working_set": len(prompt_context.working_set_block or "") if prompt_context else 0,
                "artifact_snapshot": len(prompt_context.artifact_snapshot or "") if prompt_context else 0,
                "prompt_memory": len(prompt_context.prompt_memory_block or "") if prompt_context else 0,
            },
        }
