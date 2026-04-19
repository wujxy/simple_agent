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


@dataclass
class Event:
    event_id: str
    session_id: str
    type: str
    source: str
    payload: dict = field(default_factory=dict)
    turn_id: str | None = None
    ts: float = 0.0
