from __future__ import annotations

from simple_agent.engine.dispatcher import dispatch_action
from simple_agent.engine.query_state import QueryState
from simple_agent.engine.transitions import (
    Transition,
    apply_transition,
    state_to_result,
    sync_state_to_turn,
)
from simple_agent.sessions.schemas import QueryParam
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("query_loop")


async def query_loop(state: QueryState, deps: QueryParam) -> dict:
    while not state.is_terminal():
        # Suspend on waiting states
        if state.mode in ("waiting_user_input", "waiting_user_approval"):
            break

        if not state.can_continue():
            state = apply_transition(state, Transition(
                type="failed",
                reason="max_steps_exceeded",
                message=f"Reached max step limit ({state.max_steps}) without completing the task.",
            ))
            sync_state_to_turn(state, deps.turn)
            deps.session_store.save_turn(deps.turn)
            break

        state.step_count += 1
        logger.info("Step %d/%d [%s]", state.step_count, state.max_steps, state.mode)

        # Build context
        context = await deps.context_service.build_context(deps.session, deps.turn, state)

        # Build prompt
        tool_descriptions = deps.tool_executor._registry.tool_descriptions_for_prompt()
        prompt = deps.prompt_service.build_action_prompt(state, context, tool_descriptions)

        # Call LLM
        try:
            llm_output = await deps.llm_service.generate(prompt)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            state = apply_transition(state, Transition(
                type="failed", reason="llm_error",
                message=f"LLM call failed: {e}",
            ))
            sync_state_to_turn(state, deps.turn)
            deps.session_store.save_turn(deps.turn)
            break

        # Parse action
        action = deps.parser.safe_parse(llm_output)
        if action is None:
            state.parse_fail_count += 1
            logger.warning(
                "Parse failed %d/%d on step %d. LLM output: %s",
                state.parse_fail_count, state.max_parse_fails, state.step_count,
                llm_output[:500],
            )
            await deps.memory_service.add_system_note(
                state.session_id,
                f"Warning: Failed to parse LLM output (attempt {state.parse_fail_count}). "
                f"Output started with: {llm_output[:150]}. "
                "Remember: respond with ONLY valid JSON starting with { and ending with }.",
            )
            logger.warning("Parse failed %d/%d on step %d",
                           state.parse_fail_count, state.max_parse_fails, state.step_count)
            if state.parse_fail_count >= state.max_parse_fails:
                state = apply_transition(state, Transition(
                    type="failed", reason="max_parse_fails_exceeded",
                    message="LLM output could not be parsed repeatedly.",
                ))
                sync_state_to_turn(state, deps.turn)
                deps.session_store.save_turn(deps.turn)
                break
            sync_state_to_turn(state, deps.turn)
            deps.session_store.save_turn(deps.turn)
            continue

        state.parse_fail_count = 0
        state.last_action = action.model_dump()

        # Dispatch action → get transition
        transition = await dispatch_action(action, state, deps)
        state = apply_transition(state, transition)

        # Sync state to turn after every transition
        sync_state_to_turn(state, deps.turn)
        deps.session_store.save_turn(deps.turn)

    return state_to_result(state)
