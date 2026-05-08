from __future__ import annotations

from simple_agent.schemas import ToolResult


def tool_result_to_observation_dict(result: ToolResult) -> dict:
    """Project a ToolResult into the stable runtime/memory shape."""
    obs = result.observation
    return {
        "tool_name": result.tool,
        "ok": obs.ok,
        "status": obs.status,
        "summary": obs.summary,
        "facts": obs.facts,
        "data": obs.data,
        "error": obs.error,
        "changed_paths": obs.changed_paths,
        "memory": obs.memory,
        "artifacts": obs.artifacts,
        "display": obs.display,
        "diagnostics": obs.diagnostics,
        "metadata": obs.metadata,
    }
