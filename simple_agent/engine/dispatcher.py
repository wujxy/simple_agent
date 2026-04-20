from __future__ import annotations

from simple_agent.engine.query_state import QueryState
from simple_agent.engine.transitions import Transition
from simple_agent.schemas import AgentAction
from simple_agent.sessions.schemas import QueryParam
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("dispatcher")


async def dispatch_action(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    handlers = {
        "tool_call": _handle_tool_call,
        "plan": _handle_plan,
        "replan": _handle_replan,
        "verify": _handle_verify,
        "summarize": _handle_summarize,
        "ask_user": _handle_ask_user,
        "finish": _handle_finish,
    }
    handler = handlers.get(action.type)
    if handler is None:
        logger.warning("Unknown action type: %s", action.type)
        return Transition(type="continue", reason=f"Unknown action type: {action.type}")
    return await handler(action, state, deps)


async def _handle_tool_call(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    tool_name = action.tool or ""
    args = action.args or {}

    result = await deps.tool_executor.execute(
        state.session_id, state.turn_id, tool_name, args
    )

    if result.approval_required:
        return Transition(
            type="wait_user_approval",
            reason="tool_requires_approval",
            message=result.approval_message or f"Tool '{tool_name}' requires approval.",
            payload={
                "tool_name": tool_name,
                "args": args,
                "request_id": result.approval_request_id,
            },
        )

    if result.context_required:
        await deps.memory_service.add_system_note(
            state.session_id,
            f"Context required for {tool_name}: {result.context_message}",
        )
        state.last_tool_result = {
            "tool_name": result.tool,
            "success": False,
            "output": None,
            "error": result.context_message,
        }
        return Transition(type="continue", reason=f"context_required: {tool_name}")

    result_dict = {
        "tool_name": result.tool,
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }
    await deps.memory_service.record_tool_result(
        state.session_id, state.turn_id, result_dict
    )
    state.last_tool_result = result_dict

    result_str = result.output if result.success else f"Error: {result.error}"
    await deps.memory_service.add_system_note(
        state.session_id,
        f"{tool_name}({args}) -> {result_str[:200]}",
    )

    if state.current_plan:
        for step in state.current_plan.get("steps", []):
            if step.get("status") == "pending":
                step["status"] = "done" if result.success else "failed"
                step["notes"] = result_str[:200]
                break
        deps.session_store.save_session(deps.session)

    logger.info("Tool: %s(%s) -> %s", tool_name, args, result_str[:100])
    return Transition(type="continue", reason=f"tool_call executed: {tool_name}")


async def _handle_plan(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    plan = await deps.planner.generate_plan(state.user_message)
    state.current_plan = plan.model_dump()
    await deps.memory_service.add_system_note(
        state.session_id,
        f"Plan created: {plan.summary or plan.goal}",
    )
    logger.info("Plan created: %d steps", len(plan.steps))
    return Transition(type="continue", reason="plan_created")


async def _handle_replan(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    new_plan = await deps.planner.replan(state)
    state.current_plan = new_plan
    deps.session.current_plan = new_plan
    deps.session_store.save_session(deps.session)
    await deps.memory_service.add_system_note(
        state.session_id,
        f"Replanned: {new_plan.get('summary', 'updated plan')}",
    )
    logger.info("Replanned: %d steps", len(new_plan.get("steps", [])))
    return Transition(type="continue", reason="replanned")


async def _handle_verify(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    context = await deps.context_service.build_context(deps.session, deps.turn)
    verify_result = await deps.verifier.verify(deps.session, state, context)
    state.last_verify_result = verify_result

    if verify_result.get("complete", True):
        await deps.memory_service.add_system_note(
            state.session_id,
            "Verification passed: task appears complete.",
        )
        return Transition(type="continue", reason="verify_passed")

    missing = verify_result.get("missing", "unknown")
    await deps.memory_service.add_system_note(
        state.session_id,
        f"Verification note: {missing}",
    )
    logger.warning("Verification incomplete: %s", missing)
    return Transition(type="continue", reason=f"verify_incomplete: {missing}")


async def _handle_summarize(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    context = await deps.context_service.build_context(deps.session, deps.turn)
    prompt = deps.prompt_service.build_summary_prompt(state, context)
    summary = await deps.llm_service.generate(prompt)
    state.last_summary = summary
    await deps.memory_service.add_system_note(
        state.session_id,
        f"Progress summary: {summary[:300]}",
    )
    logger.info("Summarized (%d chars)", len(summary))
    return Transition(type="continue", reason="summarized")


async def _handle_ask_user(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    return Transition(
        type="wait_user_input",
        reason="ask_user",
        message=(action.message or "Agent is asking a question.") + "\n(Type your answer to continue)",
    )


async def _handle_finish(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    context = await deps.context_service.build_context(deps.session, deps.turn)
    verify_result = await deps.verifier.verify(deps.session, state, context)
    state.last_verify_result = verify_result

    if not verify_result.get("complete", True):
        state.verify_fail_count += 1
        if state.verify_fail_count >= state.max_verify_fails:
            logger.warning("Max verify fails (%d) reached, forcing completion", state.max_verify_fails)
            return Transition(
                type="completed",
                reason="max_verify_fails_forced_complete",
                message=action.message or "Task completed (verify limit reached).",
            )
        missing = verify_result.get("missing", "unknown")
        await deps.memory_service.add_system_note(
            state.session_id,
            f"Verification note: {missing}",
        )
        logger.warning("Verify fail %d/%d: %s", state.verify_fail_count, state.max_verify_fails, missing)
        return Transition(type="continue", reason=f"verify_failed: {missing}")

    await deps.memory_service.add_system_note(
        state.session_id,
        f"Agent finished: {action.message}",
    )
    return Transition(
        type="completed",
        reason="finish_verified",
        message=action.message or "Task completed.",
    )
