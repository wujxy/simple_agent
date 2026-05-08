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
from simple_agent.runtime.event_bus import EventBus
from simple_agent.runtime.events import publish_runtime_event
from simple_agent.runtime.event_types import (
    RUNTIME_TOOL_COMPLETED,
    RUNTIME_TOOL_STARTED,
    RUNTIME_TURN_COMPLETED,
    RUNTIME_TURN_STARTED,
)
from simple_agent.runtime.modes import ModeService, RunMode
from simple_agent.sessions.schemas import QueryLoopResult, QueryParam
from simple_agent.sessions.session_service import SessionService
from simple_agent.sessions.session_store import SessionStore
from simple_agent.tools.core.executor import ToolExecutor
from simple_agent.tools.core.results import tool_result_to_observation_dict
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
        event_bus: EventBus | None = None,
        mode_service: ModeService | None = None,
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
        self._event_bus = event_bus
        self._mode_service = mode_service
        self._config = config or {}

    async def submit_message(self, session_id: str, user_text: str, run_mode: str | RunMode | None = None) -> QueryLoopResult:
        session = self._session_store.get_session(session_id)
        if session is None:
            return QueryLoopResult(status="failed", message=f"Session '{session_id}' not found")

        selected_mode = self._resolve_run_mode(session, run_mode)
        policy = self._mode_service.policy_for_mode(selected_mode) if self._mode_service else None
        max_steps = policy.max_steps if policy else self._config.get("runtime", {}).get("max_steps", 20)
        turn = self._session_store.create_turn(session_id, user_text, max_steps, selected_mode.value)
        if self._mode_service:
            self._mode_service.start_turn(session_id, turn.turn_id, selected_mode)
        await publish_runtime_event(
            self._event_bus,
            RUNTIME_TURN_STARTED,
            session_id=session_id,
            turn_id=turn.turn_id,
            source="query_engine",
            payload={
                "user_message": user_text,
                "max_steps": max_steps,
                "mode": "running",
                "run_mode": selected_mode.value,
            },
        )

        await self._context_service.append_message_event(session_id, "user", user_text, turn.turn_id)
        await self._memory_service.record_user_message(session_id, user_text)

        state = QueryState(
            session_id=session_id,
            turn_id=turn.turn_id,
            user_message=user_text,
            max_steps=max_steps,
            run_mode=selected_mode.value,
            current_plan=session.current_plan,
        )

        session.active_turn_id = turn.turn_id
        self._session_store.save_session(session)

        deps = self._build_deps(session, turn)
        result = await query_loop(state, deps)
        await self._publish_turn_completed(session_id, turn, result)
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
        if self._mode_service:
            self._mode_service.start_turn(session_id, turn.turn_id, state.run_mode)

        await self._context_service.append_message_event(session_id, "user", user_text, turn.turn_id)
        await self._memory_service.record_user_message(session_id, user_text)
        state.mode = "running"
        state.pending_action = None

        deps = self._build_deps(session, turn)
        result = await query_loop(state, deps)
        await self._publish_turn_completed(session_id, turn, result)
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
        if self._mode_service:
            self._mode_service.start_turn(session_id, turn.turn_id, state.run_mode)

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

            await publish_runtime_event(
                self._event_bus,
                RUNTIME_TOOL_STARTED,
                session_id=session_id,
                turn_id=turn.turn_id,
                step=state.step_count,
                source="query_engine",
                payload={
                    "tool_name": tool_name,
                    "args": tool_args,
                    "target": tool_args.get("path") or tool_args.get("command") or "",
                    "approved": True,
                    "run_mode": state.run_mode,
                },
            )
            result = await self._tool_executor.execute(
                session_id, turn.turn_id, tool_name, tool_args, approved=True
            )
            obs = result.observation
            result_dict = tool_result_to_observation_dict(result)
            await self._memory_service.record_tool_result(
                session_id, turn.turn_id, result_dict, step=state.step_count,
            )
            state.last_tool_result = result_dict
            await self._context_service.update_artifacts_from_tool(
                session_id, tool_name, result_dict, state.step_count,
            )
            await publish_runtime_event(
                self._event_bus,
                RUNTIME_TOOL_COMPLETED,
                session_id=session_id,
                turn_id=turn.turn_id,
                step=state.step_count,
                source="query_engine",
                payload={
                    "tool_name": tool_name,
                    "args": tool_args,
                    "target": tool_args.get("path") or tool_args.get("command") or "",
                    "ok": result_dict.get("ok", False),
                    "status": result_dict.get("status", ""),
                    "summary": result_dict.get("summary", ""),
                    "facts": result_dict.get("facts", []),
                    "changed_paths": result_dict.get("changed_paths", []),
                    "error": result_dict.get("error"),
                    "errors": result_dict.get("errors", []),
                    "run_mode": state.run_mode,
                },
            )

            if obs.ok and obs.summary:
                note = obs.summary
            elif obs.ok:
                note = f"{tool_name}({tool_args}) -> ok"
            else:
                note = f"{tool_name}({tool_args}) -> failed: {(obs.error or '')[:200]}"
            await self._memory_service.add_system_note(session_id, note)

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
        await self._publish_turn_completed(session_id, turn, result)
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
            event_bus=self._event_bus,
            mode_service=self._mode_service,
        )

    async def _publish_turn_completed(self, session_id: str, turn, result: QueryLoopResult) -> None:
        await publish_runtime_event(
            self._event_bus,
            RUNTIME_TURN_COMPLETED,
            session_id=session_id,
            turn_id=turn.turn_id,
            source="query_engine",
            payload={
                "status": result.status,
                "message": result.message,
                "step_count": turn.step_count,
                "mode": turn.mode,
                "run_mode": getattr(turn, "run_mode", "normal"),
            },
        )

    def _resolve_run_mode(self, session, run_mode: str | RunMode | None) -> RunMode:
        if self._mode_service:
            return self._mode_service.normalize_mode(run_mode or getattr(session, "run_mode", None))
        try:
            return RunMode(str(run_mode or getattr(session, "run_mode", "normal")))
        except ValueError:
            return RunMode.NORMAL

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
