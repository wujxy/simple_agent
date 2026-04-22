from __future__ import annotations

from simple_agent.engine.query_state import QueryState
from simple_agent.llm.llm_service import LLMService
from simple_agent.prompts.planner_prompt import build_planner_prompt, build_replan_prompt
from simple_agent.schemas import ExecutionPlan, ExecutionPlanStep, PlanStep, TaskPlan
from simple_agent.utils.json_utils import extract_json_from_text
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("planner")


class Planner:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    def needs_planning(self, user_request: str) -> bool:
        simple_indicators = [
            "read", "show", "list", "what", "tell me",
            "summarize", "explain", "describe",
        ]
        lower = user_request.lower().strip()
        if len(lower.split()) <= 5:
            for indicator in simple_indicators:
                if lower.startswith(indicator):
                    return False
        return True

    async def generate_plan(self, user_request: str) -> ExecutionPlan | None:
        prompt = build_planner_prompt(user_request)
        response = await self._llm.generate(prompt)
        data = extract_json_from_text(response)

        if data is None:
            logger.warning("Planner failed to parse LLM output, returning None for direct execution")
            return None

        try:
            steps = [
                ExecutionPlanStep(
                    step_id=s.get("step_id", s.get("id", f"S{i + 1}")),
                    title=s.get("title", f"Step {i + 1}"),
                    purpose=s.get("purpose", ""),
                    action_type=s.get("action_type", "inspect"),
                    target_files=s.get("target_files", []),
                    entry_conditions=s.get("entry_conditions", []),
                    completion_criteria=s.get("completion_criteria", []),
                    preferred_tools=s.get("preferred_tools", []),
                    status="pending",
                )
                for i, s in enumerate(data.get("steps", []))
            ]
            return ExecutionPlan(
                overview=data.get("overview", data.get("goal", user_request)),
                deliverables=data.get("deliverables", []),
                likely_files=data.get("likely_files", []),
                verification_targets=data.get("verification_targets", []),
                steps=steps,
            )
        except (KeyError, TypeError) as e:
            logger.warning("Planner parse error: %s, returning None", e)
            return None

    async def maybe_plan(self, user_message: str) -> dict | None:
        # Deprecated: kept for backward compatibility
        if not self.needs_planning(user_message):
            return None
        plan = await self.generate_plan(user_message)
        if plan is None:
            return None
        return plan.model_dump()

    async def replan(self, state: QueryState) -> dict | None:
        plan_data = state.current_plan
        if not plan_data:
            plan = await self.generate_plan(state.user_message)
            return plan.model_dump() if plan else None

        completed = [
            s.get("title", "") for s in plan_data.get("steps", [])
            if s.get("status") in ("done", "candidate_done")
        ]
        failed_step = "unknown"
        for s in plan_data.get("steps", []):
            if s.get("status") not in ("done", "candidate_done", "pending", "skipped"):
                failed_step = s.get("title", "unknown")
                break

        reason = "Agent requested replan"
        if state.last_action:
            reason = state.last_action.get("reason", reason)

        prompt = build_replan_prompt(state.user_message, failed_step, reason, completed)
        response = await self._llm.generate(prompt)
        data = extract_json_from_text(response)

        if data is None:
            logger.warning("Replan failed to parse, returning existing plan")
            return plan_data

        try:
            steps = [
                ExecutionPlanStep(
                    step_id=s.get("step_id", s.get("id", f"S{i + 1}")),
                    title=s.get("title", f"Step {i + 1}"),
                    purpose=s.get("purpose", ""),
                    action_type=s.get("action_type", "inspect"),
                    target_files=s.get("target_files", []),
                    entry_conditions=s.get("entry_conditions", []),
                    completion_criteria=s.get("completion_criteria", []),
                    preferred_tools=s.get("preferred_tools", []),
                    status="pending",
                )
                for i, s in enumerate(data.get("steps", []))
            ]
            new_plan = ExecutionPlan(
                overview=data.get("overview", data.get("goal", state.user_message)),
                deliverables=data.get("deliverables", []),
                likely_files=data.get("likely_files", []),
                verification_targets=data.get("verification_targets", []),
                steps=steps,
            )
            return new_plan.model_dump()
        except (KeyError, TypeError) as e:
            logger.warning("Replan parse error: %s, returning existing plan", e)
            return plan_data

    def _fallback_plan(self, user_request: str) -> TaskPlan:
        # Deprecated: kept for backward compatibility
        return TaskPlan(
            goal=user_request,
            steps=[PlanStep(id="1", title="Complete the task", description=user_request)],
            summary="Single-step fallback plan",
        )
