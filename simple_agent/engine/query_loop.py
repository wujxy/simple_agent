from __future__ import annotations

from simple_agent.sessions.schemas import QueryLoopResult, QueryParam
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("query_loop")


async def query_loop(param: QueryParam) -> QueryLoopResult:
    session = param.session
    turn = param.turn

    while turn.status not in ("completed", "failed", "waiting_user"):
        if turn.step_count >= turn.max_steps:
            logger.warning("Max steps (%d) reached", turn.max_steps)
            turn.status = "failed"
            param.session_store.save_turn(turn)
            return QueryLoopResult(
                status="failed",
                message=f"Reached max step limit ({turn.max_steps}) without completing the task.",
            )

        turn.step_count += 1
        logger.info("Step %d/%d", turn.step_count, turn.max_steps)

        # 1. Build context
        context = await param.context_service.build_context(session, turn)

        # 2. Build prompt
        tool_descriptions = param.tool_executor._registry.tool_descriptions_for_prompt()
        prompt = param.prompt_service.build_action_prompt(session, turn, context, tool_descriptions)

        # 3. Call LLM
        try:
            llm_output = await param.llm_service.generate(prompt)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            turn.status = "failed"
            param.session_store.save_turn(turn)
            return QueryLoopResult(status="failed", message=f"LLM call failed: {e}")

        # 4. Parse action
        action = param.parser.safe_parse(llm_output)
        if action is None:
            await param.memory_service.add_system_note(
                session.session_id,
                "Warning: Failed to parse LLM output, retrying",
            )
            logger.warning("Parse failed on step %d", turn.step_count)
            param.session_store.save_turn(turn)
            continue

        turn.current_action = action.model_dump()

        # 5. Branch on action type
        if action.type == "finish":
            await param.memory_service.add_system_note(
                session.session_id,
                f"Agent finished: {action.message}",
            )

            # Verify before finishing
            context = await param.context_service.build_context(session, turn)
            verify_result = await param.verifier.verify(session, turn, context)
            turn.verification_result = verify_result

            if not verify_result.get("complete", True):
                missing = verify_result.get("missing", "unknown")
                await param.memory_service.add_system_note(
                    session.session_id,
                    f"Verification note: {missing}",
                )
                logger.warning("Verification found incomplete: %s", missing)
                param.session_store.save_turn(turn)
                continue

            turn.status = "completed"
            turn.finished_at = _now()
            param.session_store.save_turn(turn)
            return QueryLoopResult(
                status="completed",
                message=action.message or "Task completed.",
                final_action=turn.current_action,
            )

        elif action.type == "ask_user":
            turn.status = "waiting_user"
            param.session_store.save_turn(turn)
            return QueryLoopResult(
                status="waiting_user",
                message=action.message or "Agent is asking a question.",
                final_action=turn.current_action,
            )

        elif action.type == "replan":
            new_plan = await param.planner.replan(session, turn)
            session.current_plan = new_plan
            param.session_store.save_session(session)
            await param.memory_service.add_system_note(
                session.session_id,
                f"Replanned: {new_plan.get('summary', 'updated plan')}",
            )
            logger.info("Replanned: %d steps", len(new_plan.get("steps", [])))
            param.session_store.save_turn(turn)
            continue

        elif action.type == "tool_call":
            result = await param.tool_executor.execute(
                session.session_id,
                turn.turn_id,
                action.tool or "",
                action.args or {},
            )

            result_dict = {
                "tool_name": result.tool,
                "success": result.success,
                "output": result.output,
                "error": result.error,
            }
            await param.memory_service.record_tool_result(
                session.session_id, turn.turn_id, result_dict
            )
            turn.last_tool_result = result_dict

            result_str = result.output if result.success else f"Error: {result.error}"
            await param.memory_service.add_system_note(
                session.session_id,
                f"{action.tool}({action.args}) -> {result_str[:200]}",
            )

            # Update plan step status
            if session.current_plan:
                for step in session.current_plan.get("steps", []):
                    if step.get("status") == "pending":
                        step["status"] = "done" if result.success else "failed"
                        step["notes"] = result_str[:200]
                        break
                param.session_store.save_session(session)

            logger.info(
                "Step %d: %s(%s) -> %s",
                turn.step_count,
                action.tool,
                action.args,
                result_str[:100],
            )

        param.session_store.save_turn(turn)

    turn.status = "failed"
    turn.finished_at = _now()
    param.session_store.save_turn(turn)
    return QueryLoopResult(status="failed", message="Query loop exited unexpectedly.")


def _now() -> float:
    import time
    return time.time()
