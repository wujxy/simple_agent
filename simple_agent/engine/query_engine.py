from __future__ import annotations

from simple_agent.context.context_service import ContextService
from simple_agent.engine.parser import ActionParser
from simple_agent.engine.planner import Planner
from simple_agent.engine.prompt_service import PromptService
from simple_agent.engine.query_loop import query_loop
from simple_agent.engine.verifier import Verifier
from simple_agent.llm.llm_service import LLMService
from simple_agent.memory.memory_service import MemoryService
from simple_agent.sessions.schemas import QueryLoopResult, QueryParam
from simple_agent.sessions.session_service import SessionService
from simple_agent.sessions.session_store import SessionStore
from simple_agent.tools.tool_executor import ToolExecutor
from simple_agent.tracing.tracing_service import TracingService
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("query_engine")


class QueryEngine:
    def __init__(
        self,
        session_store: SessionStore,
        session_service: SessionService,
        memory_service: MemoryService,
        context_service: ContextService,
        prompt_service: PromptService,
        llm_service: LLMService,
        tool_executor: ToolExecutor,
        planner: Planner,
        verifier: Verifier,
        parser: ActionParser,
        tracing_service: TracingService,
        config: dict | None = None,
    ) -> None:
        self._session_store = session_store
        self._session_service = session_service
        self._memory_service = memory_service
        self._context_service = context_service
        self._prompt_service = prompt_service
        self._llm_service = llm_service
        self._tool_executor = tool_executor
        self._planner = planner
        self._verifier = verifier
        self._parser = parser
        self._tracing_service = tracing_service
        self._config = config or {}

    async def submit_message(self, session_id: str, user_text: str) -> QueryLoopResult:
        session = self._session_store.get_session(session_id)
        if session is None:
            return QueryLoopResult(status="failed", message=f"Session '{session_id}' not found")

        max_steps = self._config.get("runtime", {}).get("max_steps", 20)
        turn = self._session_store.create_turn(session_id, user_text, max_steps)

        await self._session_service.append_message(session_id, "user", user_text)
        await self._memory_service.record_user_message(session_id, user_text)

        # Optional planning
        plan = await self._planner.maybe_plan(session, turn)
        if plan:
            session.current_plan = plan
            self._session_store.save_session(session)
            await self._memory_service.add_system_note(
                session_id,
                f"Plan: {plan.get('summary', plan.get('goal', ''))}",
            )

        param = QueryParam(
            session=session,
            turn=turn,
            session_store=self._session_store,
            session_service=self._session_service,
            memory_service=self._memory_service,
            context_service=self._context_service,
            prompt_service=self._prompt_service,
            llm_service=self._llm_service,
            tool_executor=self._tool_executor,
            planner=self._planner,
            verifier=self._verifier,
            parser=self._parser,
            tracing_service=self._tracing_service,
        )

        result = await query_loop(param)

        # Update session state based on result
        if result.status == "completed":
            session.status = "active"
        elif result.status == "waiting_user":
            session.status = "waiting_user"
        else:
            session.status = "active"
        self._session_store.save_session(session)

        return result
