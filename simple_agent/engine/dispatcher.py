from __future__ import annotations

from simple_agent.tools.core.guards import check_read_after_write, check_write_without_evidence
from simple_agent.engine.query_state import QueryState
from simple_agent.engine.transitions import Transition
from simple_agent.schemas import AgentAction, ToolResult
from simple_agent.sessions.schemas import QueryParam
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("dispatcher")

# Counts consecutive successful tools without step advancement
_consecutive_success_count: dict[str, int] = {}


def _evaluate_step_completion(
    state: QueryState, tool_name: str, result_dict: dict,
) -> None:
    """Two-layer evidence-based step completion."""
    plan = state.current_plan
    if not plan:
        return

    steps = plan.get("steps", [])
    pending_step = None
    for s in steps:
        if s.get("status") == "pending":
            pending_step = s
            break

    if pending_step is None:
        return

    action_type = pending_step.get("action_type", "")
    ok = result_dict.get("ok", False)
    step_id = pending_step.get("step_id", "?")
    key = f"{state.session_id}:{state.turn_id}:{step_id}"

    # Layer 1: Structural completion -> candidate_done
    advanced = False

    if action_type == "modify" and tool_name == "write_file" and ok:
        pending_step["status"] = "candidate_done"
        pending_step["notes"] = result_dict.get("summary", "")
        advanced = True
    elif action_type == "run" and tool_name == "bash" and ok:
        pending_step["status"] = "candidate_done"
        pending_step["notes"] = result_dict.get("summary", "")
        advanced = True
    elif action_type == "inspect" and tool_name in ("list_dir", "read_file") and ok:
        pending_step["status"] = "candidate_done"
        pending_step["notes"] = result_dict.get("summary", "")
        advanced = True
    elif action_type == "read" and tool_name == "read_file" and ok:
        pending_step["status"] = "candidate_done"
        pending_step["notes"] = result_dict.get("summary", "")
        advanced = True

    # Layer 2: Semantic completion -> done
    # If the previous step was candidate_done and this tool provides verification
    if not advanced:
        for s in steps:
            if s.get("status") == "candidate_done":
                prev_action_type = s.get("action_type", "")
                # modify step + successful run/verify -> done
                if prev_action_type == "modify" and tool_name in ("bash",) and ok:
                    s["status"] = "done"
                    s["notes"] = (s.get("notes") or "") + f" | Verified by {tool_name}"
                    advanced = True
                    break
                # run step + successful subsequent verification -> done
                elif prev_action_type == "run" and ok:
                    s["status"] = "done"
                    s["notes"] = (s.get("notes") or "") + f" | Confirmed by {tool_name}"
                    advanced = True
                    break

    # Track consecutive successes without advancement
    if advanced:
        _consecutive_success_count[key] = 0
    else:
        _consecutive_success_count[key] = _consecutive_success_count.get(key, 0) + 1
        if _consecutive_success_count[key] >= 3:
            # Mark as blocked instead of force-advancing
            pending_step["status"] = "blocked"
            pending_step["notes"] = (
                "Step blocked: multiple successful actions have not "
                "satisfied completion criteria. Consider replanning."
            )
            _consecutive_success_count[key] = 0
            logger.warning("Step %s marked as blocked", step_id)


def _obs_to_dict(result) -> dict:
    """Convert ToolResult.observation to the dict format stored in memory/state."""
    obs = result.observation
    return {
        "tool_name": result.tool,
        "ok": obs.ok,
        "status": obs.status,
        "summary": obs.summary,
        "facts": obs.facts,
        "data": obs.data,
        "error": obs.error,
        "changed_paths": obs.changed_paths,
    }


async def dispatch_action(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    handlers = {
        "tool_call": _handle_tool_call,
        "tool_batch": _handle_tool_batch,
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

    # Runtime guards
    guard_result = await check_write_without_evidence(tool_name, args, state.last_tool_result)
    if guard_result is None:
        guard_result = await check_read_after_write(tool_name, args, state.last_tool_result)

    if guard_result is not None:
        result = ToolResult(
            observation=guard_result,
            tool=tool_name,
            args=args,
        )
    else:
        result = await deps.tool_executor.execute(
        state.session_id, state.turn_id, tool_name, args
    )
    obs = result.observation

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

    if obs.status == "context_required":
        await deps.memory_service.add_system_note(
            state.session_id,
            f"Context required for {tool_name}: {obs.error}",
        )
        state.last_tool_result = _obs_to_dict(result)
        return Transition(type="continue", reason=f"context_required: {tool_name}")

    result_dict = _obs_to_dict(result)
    await deps.memory_service.record_tool_result(
        state.session_id, state.turn_id, result_dict
    )
    state.last_tool_result = result_dict

    # Update artifact state from tool result
    deps.context_service.update_artifacts_from_tool(
        tool_name, result_dict, state.step_count,
    )

    # Update working set
    if obs.ok:
        if tool_name == "read_file" and "path" in args:
            deps.session.working_set.record_read(args["path"])
        elif tool_name == "write_file" and "path" in args:
            deps.session.working_set.record_write(args["path"])
    deps.session.working_set.record_action({"tool": tool_name, "args": args})

    # System note
    if obs.ok and obs.summary:
        note = obs.summary
    elif obs.ok:
        note = f"{tool_name}({args}) -> ok"
    else:
        note = f"{tool_name}({args}) -> failed: {(obs.error or '')[:200]}"
    await deps.memory_service.add_system_note(state.session_id, note)

    # Evidence-based step completion (two-layer)
    if state.current_plan and obs.ok:
        _evaluate_step_completion(state, tool_name, result_dict)
        deps.session_store.save_session(deps.session)

    logger.info("Tool: %s(%s) -> %s", tool_name, args, obs.summary[:100])
    return Transition(type="continue", reason=f"tool_call executed: {tool_name}")


async def _handle_plan(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    plan = await deps.planner.generate_plan(state.user_message)
    if plan is None:
        await deps.memory_service.add_system_note(
            state.session_id,
            "Plan generation failed. Continuing in direct execution mode.",
        )
        return Transition(type="continue", reason="plan_failed_direct_mode")

    plan_dict = plan.model_dump()
    state.current_plan = plan_dict
    deps.session.current_plan = plan_dict
    deps.session_store.save_session(deps.session)
    await deps.memory_service.add_system_note(
        state.session_id,
        f"Plan created: {plan.overview}",
    )
    logger.info("Plan created: %d steps", len(plan.steps))
    return Transition(type="continue", reason="plan_created")


async def _handle_replan(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    new_plan = await deps.planner.replan(state)
    if new_plan is None:
        await deps.memory_service.add_system_note(
            state.session_id,
            "Replan failed. Continuing with current plan or direct execution.",
        )
        return Transition(type="continue", reason="replan_failed")

    state.current_plan = new_plan
    deps.session.current_plan = new_plan
    deps.session_store.save_session(deps.session)
    overview = new_plan.get("overview") or new_plan.get("summary") or new_plan.get("goal", "updated plan")
    await deps.memory_service.add_system_note(
        state.session_id,
        f"Replanned: {overview}",
    )
    logger.info("Replanned: %d steps", len(new_plan.get("steps", [])))
    return Transition(type="continue", reason="replanned")


async def _handle_verify(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    context = await deps.context_service.build_context(deps.session, deps.turn, state)
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
    context = await deps.context_service.build_context(deps.session, deps.turn, state)
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
    context = await deps.context_service.build_context(deps.session, deps.turn, state)
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


async def _handle_tool_batch(action: AgentAction, state: QueryState, deps: QueryParam) -> Transition:
    from simple_agent.scheduler.task_scheduler import TaskSpec, TaskScheduler

    raw_actions = action.args.get("actions", [])
    if not raw_actions:
        return Transition(type="continue", reason="empty_batch")

    specs = []
    for i, act in enumerate(raw_actions):
        specs.append(TaskSpec(
            task_id=f"batch_{state.step_count}_{i}",
            tool_name=act.get("tool", ""),
            args=act.get("args", {}),
        ))

    scheduler = TaskScheduler(deps.tool_executor)

    try:
        scheduler.validate_batch(specs)
    except ValueError as e:
        await deps.memory_service.add_system_note(
            state.session_id,
            f"Batch validation failed: {e}",
        )
        return Transition(type="continue", reason=f"batch_rejected: {e}")

    results = await scheduler.schedule(specs, state.session_id, state.turn_id)

    batch_summary_parts: list[str] = []
    all_ok = True
    for r in results:
        rdict = r.result or {}
        await deps.memory_service.record_tool_result(
            state.session_id, state.turn_id, rdict,
        )
        tool = rdict.get("tool_name", "?")
        ok = rdict.get("ok", False)
        if not ok:
            all_ok = False
        summary = rdict.get("summary", "")
        if summary:
            batch_summary_parts.append(summary[:150])
        else:
            err = rdict.get("error", "")
            batch_summary_parts.append(f"{tool}({'ok' if ok else 'fail'}: {err[:100]})")

        if ok and tool == "read_file" and "path" in (r.task.args or {}):
            deps.session.working_set.record_read(r.task.args["path"])

    batch_summary = "; ".join(batch_summary_parts)
    state.last_tool_result = {
        "tool_name": "tool_batch",
        "ok": all_ok,
        "status": "success" if all_ok else "error",
        "summary": batch_summary,
    }

    await deps.memory_service.add_system_note(
        state.session_id,
        f"Batch ({len(results)} tools): {batch_summary[:300]}",
    )

    if state.current_plan and all_ok:
        # Use evidence-based completion for each tool in batch
        for r in results:
            rdict = r.result or {}
            tool = rdict.get("tool_name", "")
            if tool and rdict.get("ok"):
                _evaluate_step_completion(state, tool, rdict)
        deps.session_store.save_session(deps.session)

    logger.info("Batch: %d tools -> %s", len(results), batch_summary[:100])
    return Transition(type="continue", reason=f"batch_completed:{len(results)}_tools")
