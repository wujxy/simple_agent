from __future__ import annotations

from simple_agent.approval.approval_service import ApprovalService
from simple_agent.context.context_service import ContextService
from simple_agent.engine.parser import ActionParser
from simple_agent.engine.planner import Planner
from simple_agent.engine.prompt_service import PromptService
from simple_agent.engine.query_loop import query_loop
from simple_agent.engine.query_state import QueryState
from simple_agent.engine.transitions import rebuild_state_from_turn, sync_state_to_turn
from simple_agent.engine.verifier import Verifier
from simple_agent.llm.llm_service import LLMService
from simple_agent.memory.memory_service import MemoryService
from simple_agent.sessions.schemas import QueryLoopResult, QueryParam
from simple_agent.sessions.session_service import SessionService
from simple_agent.sessions.session_store import SessionStore
from simple_agent.tools.core.executor import ToolExecutor
from simple_agent.tracing.tracing_service import TracingService
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("query_engine")

_APPROVE_KEYWORDS = {"/approve", "y", "yes", "approve", "ok", "confirm"}
_DENY_KEYWORDS = {"/deny", "n", "no", "deny", "reject"}


def parse_approval_response(text: str) -> bool | None:
    t = text.lower().strip()
    if t in _APPROVE_KEYWORDS:
        return True
    if t in _DENY_KEYWORDS:
        return False
    return None


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
        approval_service: ApprovalService | None = None,
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
        self._approval_service = approval_service
        self._config = config or {}

    async def submit_message(self, session_id: str, user_text: str) -> QueryLoopResult:
        session = self._session_store.get_session(session_id)
        if session is None:
            return QueryLoopResult(status="failed", message=f"Session '{session_id}' not found")

        max_steps = self._config.get("runtime", {}).get("max_steps", 20)
        turn = self._session_store.create_turn(session_id, user_text, max_steps)

        await self._session_service.append_message(session_id, "user", user_text)
        await self._memory_service.record_user_message(session_id, user_text)

        state = QueryState(
            session_id=session_id,
            turn_id=turn.turn_id,
            user_message=user_text,
            max_steps=max_steps,
            current_plan=session.current_plan,
        )

        session.active_turn_id = turn.turn_id
        self._session_store.save_session(session)

        deps = self._build_deps(session, turn)
        result = await query_loop(state, deps)
        await self._finalize_turn(session, turn)
        return result

    async def resume_user_input(self, session_id: str, user_text: str) -> QueryLoopResult:
        session = self._session_store.get_session(session_id)
        if session is None or not session.active_turn_id:
            return QueryLoopResult(status="failed", message="No active turn to resume")

        turn = self._session_store.get_turn(session.active_turn_id)
        if turn is None:
            return QueryLoopResult(status="failed", message="Active turn not found")

        state = rebuild_state_from_turn(session_id, turn, turn.user_message, session=session)

        await self._memory_service.record_user_message(session_id, user_text)
        await self._session_service.append_message(session_id, "user", user_text)
        state.mode = "running"
        state.pending_action = None

        deps = self._build_deps(session, turn)
        result = await query_loop(state, deps)
        await self._finalize_turn(session, turn)
        return result

    async def resume_approval(self, session_id: str, text: str) -> QueryLoopResult:
        session = self._session_store.get_session(session_id)
        if session is None or not session.active_turn_id:
            return QueryLoopResult(status="failed", message="No active turn to resume")

        turn = self._session_store.get_turn(session.active_turn_id)
        if turn is None:
            return QueryLoopResult(status="failed", message="Active turn not found")

        if turn.pending_action is None:
            return QueryLoopResult(status="failed", message="Turn has no pending action")

        state = rebuild_state_from_turn(session_id, turn, turn.user_message, session=session)

        pending = turn.pending_action  # guaranteed non-None by check above
        payload = pending.get("payload", {})
        tool_name = payload.get("tool_name", "")
        tool_args = payload.get("args", {})
        request_id = payload.get("request_id")

        approved = parse_approval_response(text)

        if approved:
            if self._approval_service and request_id:
                await self._approval_service.approve(request_id)

            # Record approval grant for turn-scoped reuse
            from simple_agent.tools.core.types import ApprovalGrant
            self._tool_executor._approval_memory.record(ApprovalGrant(
                session_id=session_id,
                turn_id=turn.turn_id,
                tool=tool_name,
                scope="turn",
                file_path=tool_args.get("path"),
            ))

            result = await self._tool_executor.execute(
                session_id, turn.turn_id, tool_name, tool_args, approved=True
            )
            obs = result.observation
            result_dict = {
                "tool_name": result.tool,
                "ok": obs.ok,
                "status": obs.status,
                "summary": obs.summary,
                "facts": obs.facts,
                "data": obs.data,
                "error": obs.error,
                "changed_paths": obs.changed_paths,
            }
            await self._memory_service.record_tool_result(session_id, turn.turn_id, result_dict)
            state.last_tool_result = result_dict

            if obs.ok and obs.summary:
                note = obs.summary
            elif obs.ok:
                note = f"{tool_name}({tool_args}) -> ok"
            else:
                note = f"{tool_name}({tool_args}) -> failed: {(obs.error or '')[:200]}"
            await self._memory_service.add_system_note(session_id, note)

            if obs.ok:
                if tool_name == "read_file" and "path" in tool_args:
                    session.working_set.record_read(tool_args["path"])
                elif tool_name == "write_file" and "path" in tool_args:
                    session.working_set.record_write(tool_args["path"])
            session.working_set.record_action({"tool": tool_name, "args": tool_args})

            # Use the same evidence-based step completion as dispatcher
            from simple_agent.engine.dispatcher import _evaluate_step_completion
            if state.current_plan and obs.ok:
                _evaluate_step_completion(state, tool_name, result_dict)
                self._session_store.save_session(session)

        else:
            # Deny
            if self._approval_service and request_id:
                await self._approval_service.deny(request_id)

            await self._memory_service.add_system_note(
                session_id,
                f"User denied tool execution: {tool_name}",
            )
            state.last_tool_result = {
                "tool_name": tool_name,
                "success": False,
                "error": "User denied the tool execution.",
            }

        state.mode = "running"
        state.pending_action = None

        sync_state_to_turn(state, turn)
        self._session_store.save_turn(turn)

        deps = self._build_deps(session, turn)
        result = await query_loop(state, deps)
        await self._finalize_turn(session, turn)
        return result

    def _build_deps(self, session, turn) -> QueryParam:
        return QueryParam(
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

    async def _finalize_turn(self, session, turn) -> None:
        mode = turn.mode
        if mode in ("completed", "failed"):
            session.active_turn_id = None
            session.status = "active"
        elif mode in ("waiting_user_input", "waiting_user_approval"):
            session.status = "waiting_user"
        else:
            session.active_turn_id = None
            session.status = "active"
        self._session_store.save_session(session)
