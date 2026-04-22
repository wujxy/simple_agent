from __future__ import annotations

from simple_agent.context.artifact_state import ArtifactState
from simple_agent.context.context_layers import PromptContext, WorkingSet
from simple_agent.engine.query_state import QueryState
from simple_agent.memory.memory_service import MemoryService, SessionSummaryService
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
        self._summary = SessionSummaryService(memory_service)
        self._config = config or {}
        self._artifact_state = ArtifactState()

    @property
    def artifact_state(self) -> ArtifactState:
        return self._artifact_state

    def update_artifacts_from_tool(
        self, tool_name: str, result_dict: dict, step: int,
    ) -> None:
        ok = result_dict.get("ok", False)
        if not ok:
            return

        data = result_dict.get("data", {})

        if tool_name == "read_file":
            path = data.get("path", "")
            content = data.get("content", "")
            if path and content:
                self._artifact_state.update_from_read(path, content, step)

        elif tool_name == "write_file":
            path = data.get("path", "")
            operation = data.get("operation", "updated")
            if path:
                self._artifact_state.update_from_write(path, operation, step)

        elif tool_name == "bash":
            command = data.get("command", "")
            exit_code = data.get("exit_code", -1)
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            self._artifact_state.update_from_bash(command, exit_code, stdout, stderr)

    async def build_context(
        self, session: SessionState, turn: TurnState, state: QueryState,
    ) -> PromptContext:
        objective = self._build_objective_block(session, state)
        execution_state = self._build_execution_state(session, state)
        artifact_snapshot = self._build_artifact_snapshot()
        confirmed_facts = await self._build_confirmed_facts(session)
        next_decision = self._build_next_decision_point(state)
        compact_summary = await self._summary.get_compact_summary(session.session_id)
        working_set_summary = self._build_working_set(session)
        recent_obs = await self._build_recent_observations(session, turn)

        return PromptContext(
            objective_block=objective,
            execution_state=execution_state,
            artifact_snapshot=artifact_snapshot,
            confirmed_facts=confirmed_facts,
            next_decision_point=next_decision,
            compact_memory_summary=compact_summary,
            working_set_summary=working_set_summary,
            recent_observations=recent_obs,
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

    def _build_working_set(self, session: SessionState) -> str:
        ws: WorkingSet = session.working_set
        summary = ws.summarize()
        parts: list[str] = []
        if summary["recently_read"]:
            parts.append(f"Recently read: {', '.join(summary['recently_read'][-5:])}")
        if summary["recently_written"]:
            parts.append(f"Recently written: {', '.join(summary['recently_written'][-5:])}")
        if summary["repeated_actions"]:
            for ra in summary["repeated_actions"][:3]:
                parts.append(f"Repeated: {ra['key'][:60]} (x{ra['count']})")

        written_set = set(summary["recently_written"])
        read_after_write = [f for f in summary["recently_read"] if f in written_set]
        if read_after_write:
            parts.append(f"WARNING: These files were written AND then re-read: {', '.join(read_after_write)}")

        return "\n".join(parts) if parts else "(no active files)"

    async def _build_recent_observations(self, session: SessionState, turn: TurnState) -> str:
        parts: list[str] = []
        items = await self._memory.get_recent(session.session_id, limit=15)

        tool_items = [m for m in items if m.get("role") == "tool" and not m.get("ok")]
        for item in tool_items[-2:]:
            tool = item.get("tool_name", "?")
            err = item.get("error", "")
            parts.append(f"Failed: {tool} -> {err[:100]}")

        if turn.verification_result:
            complete = turn.verification_result.get("complete", True)
            parts.append(f"Last verify: {'complete' if complete else 'incomplete'}")

        return "\n".join(parts) if parts else "(no outstanding issues)"

    async def _build_confirmed_facts(self, session: SessionState) -> str:
        items = await self._memory.get_recent(session.session_id, limit=10)
        tool_items = [m for m in items if m.get("role") == "tool" and m.get("ok")]
        if not tool_items:
            return ""

        facts_lines: list[str] = []
        seen: set[str] = set()
        for item in reversed(tool_items[-3:]):
            tool_facts = item.get("facts", [])
            if tool_facts:
                for f in tool_facts:
                    if f not in seen:
                        facts_lines.append(f"- {f}")
                        seen.add(f)
            elif item.get("summary"):
                s = item["summary"]
                if s not in seen:
                    facts_lines.append(f"- {s}")
                    seen.add(s)

        return "\n".join(facts_lines) if facts_lines else ""
