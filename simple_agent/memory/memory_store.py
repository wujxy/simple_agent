from __future__ import annotations


class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, list[dict]] = {}

    def add(self, session_id: str, item: dict) -> None:
        if session_id not in self._data:
            self._data[session_id] = []
        self._data[session_id].append(item)

    def get_recent(self, session_id: str, limit: int = 10) -> list[dict]:
        entries = self._data.get(session_id, [])
        return entries[-limit:]

    def get_all(self, session_id: str) -> list[dict]:
        return list(self._data.get(session_id, []))

    def replace_all(self, session_id: str, items: list[dict]) -> None:
        self._data[session_id] = list(items)

    def count(self, session_id: str) -> int:
        return len(self._data.get(session_id, []))
