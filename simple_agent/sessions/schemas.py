from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from simple_agent.schemas import AgentAction

if TYPE_CHECKING:
    from simple_agent.context.context_service import ContextService
    from simple_agent.engine.parser import ActionParser
    from simple_agent.engine.planner import Planner
    from simple_agent.engine.verifier import Verifier
    from simple_agent.llm.llm_service import LLMService
    from simple_agent.memory.memory_service import MemoryService
    from simple_agent.sessions.session_service import SessionService
    from simple_agent.sessions.session_store import SessionStore
    from simple_agent.tools.tool_executor import ToolExecutor
    from simple_agent.tracing.tracing_service import TracingService
    from simple_agent.engine.prompt_service import PromptService


@dataclass
class SessionState:
    session_id: str
    created_at: float
    status: str = "active"  # active | waiting_user | failed | closed
    cwd: str | None = None
    message_history: list[dict[str, Any]] = field(default_factory=list)
    current_plan: dict[str, Any] | None = None
    active_turn_id: str | None = None
    permission_state: dict[str, Any] = field(default_factory=dict)
    context_meta: dict[str, Any] = field(default_factory=dict)
    memory_meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnState:
    turn_id: str
    session_id: str
    user_message: str
    status: str = "running"  # running | waiting_tool | waiting_user | completed | failed
    step_count: int = 0
    max_steps: int = 20
    current_action: dict[str, Any] | None = None
    last_tool_result: dict[str, Any] | None = None
    verification_result: dict[str, Any] | None = None
    started_at: float = 0.0
    finished_at: float | None = None


@dataclass
class QueryLoopResult:
    status: str  # completed | waiting_user | failed
    message: str
    final_action: dict[str, Any] | None = None


@dataclass
class QueryParam:
    session: SessionState
    turn: TurnState
    session_store: SessionStore
    session_service: SessionService
    memory_service: MemoryService
    context_service: ContextService
    prompt_service: PromptService
    llm_service: LLMService
    tool_executor: ToolExecutor
    planner: Planner
    verifier: Verifier
    parser: ActionParser
    tracing_service: TracingService
