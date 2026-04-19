from __future__ import annotations

from simple_agent.memory.memory_store import MemoryStore
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("memory_service")


class MemoryService:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def record_user_message(self, session_id: str, text: str) -> None:
        self._store.add(session_id, {"role": "user", "content": text})

    async def record_tool_result(self, session_id: str, turn_id: str, result: dict) -> None:
        self._store.add(session_id, {
            "role": "tool",
            "turn_id": turn_id,
            "tool_name": result.get("tool_name", "unknown"),
            "success": result.get("success", False),
            "output": result.get("output", ""),
            "error": result.get("error", ""),
        })

    async def add_system_note(self, session_id: str, note: str) -> None:
        self._store.add(session_id, {"role": "system", "content": note})

    async def get_recent(self, session_id: str, limit: int = 10) -> list[dict]:
        return self._store.get_recent(session_id, limit)
