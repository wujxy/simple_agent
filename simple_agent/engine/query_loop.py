from __future__ import annotations

from simple_agent.engine.action_utils import (
    action_display_args,
    action_tool_name,
    batch_action_targets,
)
from simple_agent.engine.dispatcher import dispatch_action
from simple_agent.engine.query_state import QueryState
from simple_agent.engine.transitions import (
    Transition,
    apply_transition,
    state_to_result,
    sync_state_to_turn,
)
from simple_agent.sessions.schemas import QueryParam
from simple_agent.runtime.events import publish_runtime_event
from simple_agent.runtime.event_types import (
    RUNTIME_ACTION_PARSED,
    RUNTIME_CONTEXT_BUDGET_UPDATED,
    RUNTIME_LLM_COMPLETED,
    RUNTIME_LLM_PROMPT_BUILT,
    RUNTIME_LLM_STARTED,
    RUNTIME_MEMORY_UPDATED,
    RUNTIME_STEP_COMPLETED,
    RUNTIME_STEP_STARTED,
)
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("query_loop")


def _estimated_tokens(chars: int) -> int:
    return (chars + 3) // 4


def _action_event_payload(action, state: QueryState) -> dict:
    args = action_display_args(action)
    payload = {
        "step": state.step_count,
        "max_steps": state.max_steps,
        "run_mode": state.run_mode,
        "action_type": action.type,
        "tool_name": action_tool_name(action),
        "args": args,
        "reason": getattr(action, "reason", ""),
    }
    if action.type == "tool_batch":
        actions = args.get("actions", [])
        payload.update({
            "batch_count": len(actions),
            "batch_tools": [item.get("tool", "?") for item in actions],
            "targets": batch_action_targets(action),
        })
    else:
        payload["target"] = (
            args.get("path") or args.get("command") or args.get("root") or args.get("pattern")
        )
    return payload


def _mode_policy_payload(deps: QueryParam, state: QueryState) -> dict:
    service = getattr(deps, "mode_service", None)
    if service is None:
        return {"run_mode": state.run_mode}
    policy = service.policy_for_mode(state.run_mode)
    usage = service.usage_snapshot(state.session_id, state.turn_id)
    return {
        "run_mode": state.run_mode,
        "mode_policy": policy.model_dump(),
        "mode_usage": usage,
    }


def _should_force_plan(state: QueryState, deps: QueryParam) -> bool:
    service = getattr(deps, "mode_service", None)
    if service is None:
        return False
    policy = service.policy_for_mode(state.run_mode)
    if not policy.planning_required or state.current_plan or state.metadata.get("plan_attempted"):
        return False
    needs_planning = getattr(deps.planner, "needs_planning", None)
    return bool(needs_planning and needs_planning(state.user_message))


def _budget_payload(deps: QueryParam, context, prompt: str) -> dict:
    prompt_stats_fn = getattr(deps.prompt_service, "last_action_prompt_stats", None)
    prompt_stats = prompt_stats_fn() if prompt_stats_fn else {}
    total_chars = int(prompt_stats.get("total_chars") or len(prompt))
    token_budget = int(getattr(deps.llm_service, "_config", {}).get("context_budget_tokens", 32000))
    estimated = _estimated_tokens(total_chars)
    token_percent = int((estimated / token_budget) * 100) if token_budget else 0
    memory_fn = getattr(deps.memory_service, "budget_snapshot", None)
    memory = memory_fn(deps.session.session_id) if memory_fn else {}
    runtime_fn = getattr(deps.context_service, "runtime_snapshot", None)
    runtime = runtime_fn(deps.session.session_id, context) if runtime_fn else {}
    return {
        "prompt": {
            "total_chars": total_chars,
            "estimated_tokens": estimated,
            "token_budget": token_budget,
            "token_percent": token_percent,
            "layers": prompt_stats.get("layers", {}),
        },
        "memory": memory,
        "working_set": runtime.get("working_set", {}),
        "artifact": runtime.get("artifact", {}),
        "projected_chars": runtime.get("projected_chars", {}),
    }


def _build_step_memory_payload(action, state: QueryState, transition: Transition) -> dict:
    payload = {
        "step": state.step_count,
        "run_mode": state.run_mode,
        "action_type": action.type,
        "tool_name": action_tool_name(action),
        "args": action_display_args(action),
        "ok": transition.type not in ("failed",),
        "summary": transition.message or transition.reason or "",
    }

    if action.type in ("tool_call", "tool_batch") and state.last_tool_result:
        tool_result = state.last_tool_result
        payload["facts"] = tool_result.get("facts", [])
        payload["changed_paths"] = tool_result.get("changed_paths", [])
        errors = tool_result.get("errors", [])
        if not isinstance(errors, list):
            errors = [errors]
        if tool_result.get("error"):
            errors.append(tool_result["error"])
        payload["errors"] = errors
        payload["summary"] = tool_result.get("summary") or payload["summary"]

    if action.type in ("verify", "finish") and state.last_verify_result:
        verify = state.last_verify_result
        verification = []
        if verify.get("reason"):
            verification.append(verify["reason"])
        if verify.get("missing"):
            verification.append(f"missing: {verify['missing']}")
        payload["verification"] = verification
        if verify.get("complete") is False:
            payload["ok"] = False
            payload["errors"] = [str(verify.get("missing") or "verification incomplete")]

    if transition.type == "failed":
        errors = payload.get("errors", [])
        if not isinstance(errors, list):
            errors = [errors]
        errors.append(transition.message or transition.reason)
        payload["errors"] = errors

    return payload


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
        await publish_runtime_event(
            getattr(deps, "event_bus", None),
            RUNTIME_STEP_STARTED,
            session_id=state.session_id,
            turn_id=state.turn_id,
            step=state.step_count,
            source="query_loop",
            payload={
                "step": state.step_count,
                "max_steps": state.max_steps,
                "mode": state.mode,
                **_mode_policy_payload(deps, state),
            },
        )

        if _should_force_plan(state, deps):
            state.metadata["plan_attempted"] = True
            plan = await deps.planner.generate_plan(state.user_message)
            if plan is not None:
                plan_dict = plan.model_dump()
                state.current_plan = plan_dict
                deps.session.current_plan = plan_dict
                deps.session_store.save_session(deps.session)
                await deps.memory_service.add_system_note(
                    state.session_id,
                    f"Plan mode created plan: {plan.overview}",
                )
                await publish_runtime_event(
                    getattr(deps, "event_bus", None),
                    RUNTIME_ACTION_PARSED,
                    session_id=state.session_id,
                    turn_id=state.turn_id,
                    step=state.step_count,
                    source="query_loop",
                    payload={
                        "ok": True,
                        "step": state.step_count,
                        "max_steps": state.max_steps,
                        "run_mode": state.run_mode,
                        "action_type": "plan",
                        "tool_name": "",
                        "args": {},
                        "reason": "plan mode requires planning for this complex task",
                    },
                )
                step_payload = {
                    "step": state.step_count,
                    "action_type": "plan",
                    "tool_name": "",
                    "args": {},
                    "ok": True,
                    "summary": plan.overview,
                }
                await deps.memory_service.record_step_event(state.session_id, step_payload)
                await deps.context_service.append_step_event(
                    state.session_id,
                    state.turn_id,
                    state.step_count,
                    step_payload,
                )
                await publish_runtime_event(
                    getattr(deps, "event_bus", None),
                    RUNTIME_STEP_COMPLETED,
                    session_id=state.session_id,
                    turn_id=state.turn_id,
                    step=state.step_count,
                    source="query_loop",
                    payload={
                        "step": state.step_count,
                        "run_mode": state.run_mode,
                        "transition_type": "continue",
                        "reason": "plan_mode_forced_plan_created",
                        "message": plan.overview,
                    },
                )
                sync_state_to_turn(state, deps.turn)
                deps.session_store.save_turn(deps.turn)
                continue

        # Build context
        context = await deps.context_service.build_context(deps.session, deps.turn, state)
        if getattr(deps, "mode_service", None) is not None:
            state.metadata["mode_policy"] = deps.mode_service.policy_for_mode(state.run_mode).model_dump()

        # Build prompt
        tool_descriptions = deps.tool_executor._registry.tool_descriptions_for_prompt()
        prompt = deps.prompt_service.build_action_prompt(
            state, context, tool_descriptions, include_batch=True,
        )
        budget_payload = _budget_payload(deps, context, prompt)
        await publish_runtime_event(
            getattr(deps, "event_bus", None),
            RUNTIME_LLM_PROMPT_BUILT,
            session_id=state.session_id,
            turn_id=state.turn_id,
            step=state.step_count,
            source="query_loop",
            payload={**budget_payload["prompt"], **_mode_policy_payload(deps, state)},
        )
        await publish_runtime_event(
            getattr(deps, "event_bus", None),
            RUNTIME_CONTEXT_BUDGET_UPDATED,
            session_id=state.session_id,
            turn_id=state.turn_id,
            step=state.step_count,
            source="query_loop",
            payload={**budget_payload, **_mode_policy_payload(deps, state)},
        )

        # Call LLM
        try:
            await publish_runtime_event(
                getattr(deps, "event_bus", None),
                RUNTIME_LLM_STARTED,
                session_id=state.session_id,
                turn_id=state.turn_id,
                step=state.step_count,
                source="query_loop",
                payload={
                    "prompt_chars": len(prompt),
                    "prompt_estimated_tokens": _estimated_tokens(len(prompt)),
                    "run_mode": state.run_mode,
                },
            )
            llm_output = await deps.llm_service.generate(prompt)
            await publish_runtime_event(
                getattr(deps, "event_bus", None),
                RUNTIME_LLM_COMPLETED,
                session_id=state.session_id,
                turn_id=state.turn_id,
                step=state.step_count,
                source="query_loop",
                payload={
                    "prompt_chars": len(prompt),
                    "prompt_estimated_tokens": _estimated_tokens(len(prompt)),
                    "response_chars": len(llm_output),
                    "run_mode": state.run_mode,
                },
            )
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
            await publish_runtime_event(
                getattr(deps, "event_bus", None),
                RUNTIME_ACTION_PARSED,
                session_id=state.session_id,
                turn_id=state.turn_id,
                step=state.step_count,
                source="query_loop",
                payload={
                    "ok": False,
                    "step": state.step_count,
                    "max_steps": state.max_steps,
                    "error": "parse_failed",
                    "output_preview": llm_output[:300],
                    "parse_fail_count": state.parse_fail_count,
                    "run_mode": state.run_mode,
                },
            )
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
        await publish_runtime_event(
            getattr(deps, "event_bus", None),
            RUNTIME_ACTION_PARSED,
            session_id=state.session_id,
            turn_id=state.turn_id,
            step=state.step_count,
            source="query_loop",
            payload={"ok": True, **_action_event_payload(action, state)},
        )
        if action.type == "tool_batch":
            actions = getattr(action, "actions", [])
            tools = ", ".join(a.tool for a in actions)
            logger.info("Step %d action: tool_batch [%s]", state.step_count, tools)
            logger.info(
                "Batch parsed step=%d actions=%d targets_preview=%s",
                state.step_count,
                len(actions),
                batch_action_targets(action)[:20],
            )
        else:
            logger.info("Step %d action: %s %s", state.step_count, action.type, action_tool_name(action))

        # Dispatch action → get transition
        transition = await dispatch_action(action, state, deps)
        step_payload = _build_step_memory_payload(action, state, transition)
        await deps.memory_service.record_step_event(state.session_id, step_payload)
        await deps.context_service.append_step_event(
            state.session_id,
            state.turn_id,
            state.step_count,
            step_payload,
        )
        await publish_runtime_event(
            getattr(deps, "event_bus", None),
            RUNTIME_MEMORY_UPDATED,
            session_id=state.session_id,
            turn_id=state.turn_id,
            step=state.step_count,
            source="query_loop",
            payload=(
                deps.memory_service.budget_snapshot(state.session_id)
                if hasattr(deps.memory_service, "budget_snapshot")
                else {}
            ),
        )
        await publish_runtime_event(
            getattr(deps, "event_bus", None),
            RUNTIME_STEP_COMPLETED,
            session_id=state.session_id,
            turn_id=state.turn_id,
            step=state.step_count,
            source="query_loop",
            payload={
                "step": state.step_count,
                "transition_type": transition.type,
                "reason": transition.reason,
                "message": transition.message,
                **_mode_policy_payload(deps, state),
            },
        )
        state = apply_transition(state, transition)

        # Sync state to turn after every transition
        sync_state_to_turn(state, deps.turn)
        deps.session_store.save_turn(deps.turn)

    return state_to_result(state)
