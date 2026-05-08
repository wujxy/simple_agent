from __future__ import annotations

from dataclasses import dataclass, field


USER_MESSAGE_RECEIVED = "user_message_received"
TURN_STARTED = "turn_started"
TURN_COMPLETED = "turn_completed"
TOOL_REQUESTED = "tool_requested"
TOOL_COMPLETED = "tool_completed"
LLM_REQUEST_STARTED = "llm_request_started"
LLM_RESPONSE_COMPLETED = "llm_response_completed"
VERIFICATION_COMPLETED = "verification_completed"

RUNTIME_TURN_STARTED = "turn.started"
RUNTIME_STEP_STARTED = "step.started"
RUNTIME_LLM_PROMPT_BUILT = "llm.prompt_built"
RUNTIME_LLM_STARTED = "llm.started"
RUNTIME_LLM_COMPLETED = "llm.completed"
RUNTIME_ACTION_PARSED = "action.parsed"
RUNTIME_TOOL_STARTED = "tool.started"
RUNTIME_TOOL_PROGRESS = "tool.progress"
RUNTIME_TOOL_COMPLETED = "tool.completed"
RUNTIME_APPROVAL_REQUIRED = "approval.required"
RUNTIME_MEMORY_UPDATED = "memory.updated"
RUNTIME_CONTEXT_BUDGET_UPDATED = "context.budget.updated"
RUNTIME_COMPACT_SUGGESTED = "compact.suggested"
RUNTIME_COMPACT_STARTED = "compact.started"
RUNTIME_COMPACT_COMPLETED = "compact.completed"
RUNTIME_STEP_COMPLETED = "step.completed"
RUNTIME_TURN_COMPLETED = "turn.completed"


@dataclass
class Event:
    event_id: str
    session_id: str
    type: str
    source: str
    payload: dict = field(default_factory=dict)
    turn_id: str | None = None
    ts: float = 0.0
