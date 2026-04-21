from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkingSet:
    recently_read_files: list[str] = field(default_factory=list)
    recently_written_files: list[str] = field(default_factory=list)
    _action_counts: dict[str, int] = field(default_factory=dict)

    @property
    def repeated_actions(self) -> list[dict]:
        return [
            {"key": k, "count": v}
            for k, v in self._action_counts.items()
            if v >= 2
        ]

    @property
    def active_files(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for f in self.recently_read_files + self.recently_written_files:
            if f not in seen:
                seen.add(f)
                result.append(f)
        return result

    def record_read(self, path: str) -> None:
        if path not in self.recently_read_files:
            self.recently_read_files.append(path)

    def record_write(self, path: str) -> None:
        if path not in self.recently_written_files:
            self.recently_written_files.append(path)

    def record_action(self, action: dict) -> None:
        tool = action.get("tool", "")
        args = action.get("args", {})
        key = f"{tool}:{sorted(args.items())}"
        self._action_counts[key] = self._action_counts.get(key, 0) + 1

    def summarize(self) -> dict:
        return {
            "recently_read": self.recently_read_files[-10:],
            "recently_written": self.recently_written_files[-10:],
            "active_files": self.active_files,
            "repeated_actions": self.repeated_actions,
        }


@dataclass
class PromptContext:
    query_state_projection: str
    working_set_summary: str
    compact_memory_summary: str
    recent_observations: str
    confirmed_facts: str = ""

    def to_dict(self) -> dict:
        return {
            "query_state_projection": self.query_state_projection,
            "working_set_summary": self.working_set_summary,
            "compact_memory_summary": self.compact_memory_summary,
            "recent_observations": self.recent_observations,
            "confirmed_facts": self.confirmed_facts,
        }
