from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryEntry:
    role: str  # user | agent | tool | system
    content: str


class Memory:
    def __init__(self, window: int = 10) -> None:
        self._entries: list[MemoryEntry] = []
        self._window = window

    def add(self, role: str, content: str) -> None:
        if content:
            self._entries.append(MemoryEntry(role=role, content=content))

    def get_recent(self, n: int | None = None) -> list[MemoryEntry]:
        n = n or self._window
        return self._entries[-n:]

    def get_all(self) -> list[MemoryEntry]:
        return list(self._entries)

    def compact_context(self) -> str:
        recent = self.get_recent()
        if not recent:
            return "(no prior context)"
        lines: list[str] = []
        for entry in recent:
            lines.append(f"[{entry.role}] {entry.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
