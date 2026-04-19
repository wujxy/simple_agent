from __future__ import annotations


class ContextCompactor:
    def compact_recent_history(self, messages: list[dict], max_items: int = 10) -> list[dict]:
        return messages[-max_items:]

    def compact_tool_outputs(self, items: list[dict], max_chars: int = 2000) -> list[dict]:
        result = []
        for item in items:
            output = item.get("output", "")
            if len(output) > max_chars:
                item = {**item, "output": output[:max_chars] + "\n... (truncated)"}
            result.append(item)
        return result
