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


class SessionSummaryService:
    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    async def get_compact_summary(self, session_id: str) -> str:
        items = await self._memory.get_recent(session_id, limit=20)
        items = [m for m in items if m.get("role") != "tool"]
        if not items:
            return "(no prior context)"

        deduped = self._dedup(items)
        lines: list[str] = []
        for item in deduped:
            role = item.get("role", "unknown")
            content = item.get("content", item.get("output", ""))
            truncate = 80 if role == "tool" else 200
            lines.append(f"[{role}] {content[:truncate]}")
        return "\n".join(lines)

    def _dedup(self, items: list[dict]) -> list[dict]:
        seen: dict[str, int] = {}
        result: list[dict] = []
        for item in items:
            role = item.get("role", "")
            content = item.get("content", item.get("output", ""))
            key = f"{role}:{content[:100]}"
            if key in seen:
                seen[key] += 1
            else:
                seen[key] = 1
                result.append(item)
        final: list[dict] = []
        for item in result:
            role = item.get("role", "")
            content = item.get("content", item.get("output", ""))
            key = f"{role}:{content[:100]}"
            count = seen[key]
            if count > 1:
                item = dict(item)
                item["content"] = f"{content} (repeated {count}x)"
            final.append(item)
        return final
