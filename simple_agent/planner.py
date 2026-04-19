from __future__ import annotations

from simple_agent.llm.base import BaseLLMClient
from simple_agent.memory import Memory
from simple_agent.prompts.planner_prompt import build_planner_prompt, build_replan_prompt
from simple_agent.schemas import PlanStep, TaskPlan
from simple_agent.utils.json_utils import extract_json_from_text
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("planner")


class Planner:
    def __init__(self, llm: BaseLLMClient) -> None:
        self._llm = llm

    def needs_planning(self, user_request: str) -> bool:
        simple_indicators = [
            "read", "show", "list", "what", "tell me",
            "summarize", "explain", "describe",
        ]
        lower = user_request.lower().strip()
        # Very short simple requests likely don't need planning
        if len(lower.split()) <= 5:
            for indicator in simple_indicators:
                if lower.startswith(indicator):
                    return False
        return True

    def generate_plan(self, user_request: str) -> TaskPlan:
        prompt = build_planner_prompt(user_request)
        response = self._llm.generate(prompt)
        data = extract_json_from_text(response)

        if data is None:
            logger.warning("Planner failed to parse, using fallback single-step plan")
            return self._fallback_plan(user_request)

        try:
            steps = [
                PlanStep(
                    id=s.get("id", str(i + 1)),
                    title=s["title"],
                    description=s.get("description", s["title"]),
                    status="pending",
                )
                for i, s in enumerate(data.get("steps", []))
            ]
            return TaskPlan(
                goal=data.get("goal", user_request),
                steps=steps,
                summary=data.get("summary"),
            )
        except (KeyError, TypeError):
            return self._fallback_plan(user_request)

    def replan(
        self,
        user_request: str,
        plan: TaskPlan,
        failed_step_id: str,
        reason: str,
    ) -> TaskPlan:
        completed = [
            s.title for s in plan.steps if s.status == "done"
        ]
        failed_step = next(
            (s.title for s in plan.steps if s.id == failed_step_id), "unknown"
        )

        prompt = build_replan_prompt(user_request, failed_step, reason, completed)
        response = self._llm.generate(prompt)
        data = extract_json_from_text(response)

        if data is None:
            return plan

        try:
            steps = [
                PlanStep(
                    id=s.get("id", str(i + 1)),
                    title=s["title"],
                    description=s.get("description", s["title"]),
                    status="pending",
                )
                for i, s in enumerate(data.get("steps", []))
            ]
            return TaskPlan(
                goal=data.get("goal", user_request),
                steps=steps,
                version=plan.version + 1,
                summary=data.get("summary"),
            )
        except (KeyError, TypeError):
            return plan

    def _fallback_plan(self, user_request: str) -> TaskPlan:
        return TaskPlan(
            goal=user_request,
            steps=[PlanStep(id="1", title="Complete the task", description=user_request)],
            summary="Single-step fallback plan",
        )
