from __future__ import annotations

import dataclasses

from simple_agent.engine.query_state import PendingAction, QueryState
from simple_agent.sessions.schemas import TurnState


@dataclasses.dataclass
class Transition:
    type: str  # continue | wait_user_input | wait_user_approval | completed | failed
    reason: str
    message: str | None = None
    payload: dict | None = None


def apply_transition(state: QueryState, transition: Transition) -> QueryState:
    state = dataclasses.replace(state)
    state.transition_reason = transition.reason

    if transition.type == "continue":
        pass
    elif transition.type == "wait_user_input":
        state.mode = "waiting_user_input"
        state.pending_action = PendingAction(
            type="user_input",
            payload=transition.payload or {},
            message=transition.message or "Waiting for user input",
        )
    elif transition.type == "wait_user_approval":
        state.mode = "waiting_user_approval"
        state.pending_action = PendingAction(
            type="user_approval",
            payload=transition.payload or {},
            message=transition.message or "Waiting for user approval",
        )
    elif transition.type == "completed":
        state.mode = "completed"
        state.finish_message = transition.message
    elif transition.type == "failed":
        state.mode = "failed"
        state.finish_message = transition.message

    return state


def sync_state_to_turn(state: QueryState, turn: TurnState) -> None:
    turn.step_count = state.step_count
    turn.mode = state.mode
    turn.status = state.mode
    turn.current_action = state.last_action
    turn.last_tool_result = state.last_tool_result
    turn.verification_result = state.last_verify_result

    if state.pending_action:
        turn.pending_action = {
            "type": state.pending_action.type,
            "payload": state.pending_action.payload,
            "message": state.pending_action.message,
        }
    else:
        turn.pending_action = None

    if state.mode in ("completed", "failed"):
        import time
        turn.finished_at = time.time()


def state_to_result(state: QueryState) -> dict:
    from simple_agent.sessions.schemas import QueryLoopResult

    if state.mode == "completed":
        return QueryLoopResult(
            status="completed",
            message=state.finish_message or "Task completed.",
            final_action=state.last_action,
        )
    elif state.mode in ("waiting_user_input", "waiting_user_approval"):
        return QueryLoopResult(
            status="waiting_user",
            message=state.pending_action.message if state.pending_action else "Waiting for user.",
            final_action=state.last_action,
        )
    else:
        return QueryLoopResult(
            status="failed",
            message=state.finish_message or "Query loop failed.",
            final_action=state.last_action,
        )


def rebuild_state_from_turn(
    session_id: str, turn: TurnState, user_message: str, session=None,
) -> QueryState:
    state = QueryState(
        session_id=session_id,
        turn_id=turn.turn_id,
        user_message=user_message,
        step_count=turn.step_count,
        max_steps=turn.max_steps,
        mode=turn.mode or turn.status,
    )

    if session and session.current_plan:
        state.current_plan = session.current_plan

    if turn.pending_action:
        state.pending_action = PendingAction(
            type=turn.pending_action.get("type", "user_input"),
            payload=turn.pending_action.get("payload", {}),
            message=turn.pending_action.get("message", ""),
        )

    state.last_action = turn.current_action
    state.last_tool_result = turn.last_tool_result
    state.last_verify_result = turn.verification_result

    return state
