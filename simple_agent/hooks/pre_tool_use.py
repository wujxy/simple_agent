from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolInvocation:
    session_id: str
    turn_id: str
    tool_name: str
    args: dict = field(default_factory=dict)
    cwd: str | None = None
    description: str | None = None


@dataclass
class HookDecision:
    status: str  # allow | deny | ask | context_required
    reason: str | None = None
    message: str | None = None
    payload: dict[str, Any] | None = None


class PreToolUseHook:
    async def before_tool_use(self, invocation: ToolInvocation) -> HookDecision:
        raise NotImplementedError
