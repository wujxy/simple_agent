from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingAction:
    type: str  # "user_input" | "user_approval"
    payload: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass
class QueryState:
    session_id: str
    turn_id: str
    user_message: str

    step_count: int = 0
    max_steps: int = 20
    verify_fail_count: int = 0
    max_verify_fails: int = 2
    parse_fail_count: int = 0
    max_parse_fails: int = 3

    mode: str = "running"
    # running | waiting_user_input | waiting_user_approval | completed | failed

    current_plan: dict[str, Any] | None = None
    last_action: dict[str, Any] | None = None
    last_tool_result: dict[str, Any] | None = None
    last_verify_result: dict[str, Any] | None = None
    last_summary: str | None = None

    pending_action: PendingAction | None = None
    transition_reason: str | None = None
    finish_message: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    # Batch task tracking
    pending_tasks: dict[str, dict] = field(default_factory=dict)
    running_tasks: dict[str, dict] = field(default_factory=dict)
    completed_tasks: dict[str, dict] = field(default_factory=dict)
    failed_tasks: dict[str, dict] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.mode in {"completed", "failed"}

    def can_continue(self) -> bool:
        return self.mode == "running" and self.step_count < self.max_steps
