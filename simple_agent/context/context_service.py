from __future__ import annotations

from simple_agent.context.context_layers import PromptContext, WorkingSet
from simple_agent.engine.query_state import QueryState
from simple_agent.memory.memory_service import MemoryService, SessionSummaryService
from simple_agent.sessions.schemas import SessionState, TurnState
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("context_service")


class ContextService:
    def __init__(self, memory_service: MemoryService, config: dict | None = None) -> None:
        self._memory = memory_service
        self._summary = SessionSummaryService(memory_service)
        self._config = config or {}

    async def build_context(
        self, session: SessionState, turn: TurnState, state: QueryState,
    ) -> PromptContext:
        query_projection = self._build_query_state_projection(state)
        working_set_summary = self._build_working_set(session)
        compact_summary = await self._summary.get_compact_summary(session.session_id)
        recent_obs = await self._build_recent_observations(session, turn)

        return PromptContext(
            query_state_projection=query_projection,
            working_set_summary=working_set_summary,
            compact_memory_summary=compact_summary,
            recent_observations=recent_obs,
        )

    def _build_query_state_projection(self, state: QueryState) -> str:
        lines = [
            f"mode={state.mode}",
            f"step={state.step_count}/{state.max_steps}",
        ]
        if state.current_plan:
            steps = state.current_plan.get("steps", [])
            done = sum(1 for s in steps if s.get("status") == "done")
            lines.append(f"plan_progress={done}/{len(steps)} steps done")
        if state.last_tool_result:
            tool = state.last_tool_result.get("tool_name", "?")
            ok = state.last_tool_result.get("success", False)
            lines.append(f"last_tool={tool}({'ok' if ok else 'failed'})")
        return "\n".join(lines)

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

        # Non-progress guard: warn if same file was both written and read
        written_set = set(summary["recently_written"])
        read_after_write = [f for f in summary["recently_read"] if f in written_set]
        if read_after_write:
            parts.append(f"WARNING: These files were written AND then re-read (do NOT read them again): {', '.join(read_after_write)}")

        return "\n".join(parts) if parts else "(no active files)"

    async def _build_recent_observations(self, session: SessionState, turn: TurnState) -> str:
        parts: list[str] = []

        # Pull recent tool results from memory (shows last 3, not just 1)
        items = await self._memory.get_recent(session.session_id, limit=15)
        tool_items = [m for m in items if m.get("role") == "tool"][-2:]
        for item in tool_items:
            tool = item.get("tool_name", "?")
            ok = item.get("success", False)
            out = item.get("output", item.get("error", ""))
            parts.append(f"Tool result: {tool} -> {'ok' if ok else 'failed'}: {str(out)[:100]}")

        if turn.verification_result:
            complete = turn.verification_result.get("complete", True)
            parts.append(f"Last verify: {'complete' if complete else 'incomplete'}")

        return "\n".join(parts) if parts else "(no recent observations)"
