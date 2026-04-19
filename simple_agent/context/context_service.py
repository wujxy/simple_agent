from __future__ import annotations

from simple_agent.context.compactor import ContextCompactor
from simple_agent.memory.memory_service import MemoryService
from simple_agent.sessions.schemas import SessionState, TurnState
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("context_service")


class ContextService:
    def __init__(self, memory_service: MemoryService, config: dict | None = None) -> None:
        self._memory = memory_service
        self._compactor = ContextCompactor()
        self._config = config or {}

    async def build_context(self, session: SessionState, turn: TurnState) -> dict:
        recent_history = self._compactor.compact_recent_history(
            session.message_history,
            self._config.get("recent_history_limit", 20),
        )
        important_memory = await self._memory.get_recent(
            session.session_id,
            self._config.get("memory_limit", 10),
        )
        important_memory = self._compactor.compact_tool_outputs(
            important_memory,
            self._config.get("max_tool_output_chars", 2000),
        )
        return {
            "recent_history": recent_history,
            "important_memory": important_memory,
            "current_plan": session.current_plan,
            "last_tool_result": turn.last_tool_result,
        }

    async def maybe_compact(self, session_id: str) -> None:
        logger.info("Context compaction check for session %s (no-op in v1)", session_id)
