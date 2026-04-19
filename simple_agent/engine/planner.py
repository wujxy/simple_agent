from __future__ import annotations

from simple_agent.llm.llm_service import LLMService
from simple_agent.prompts.planner_prompt import build_planner_prompt, build_replan_prompt
from simple_agent.schemas import PlanStep, TaskPlan
from simple_agent.sessions.schemas import SessionState, TurnState
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

    async def generate_plan(self, user_request: str) -> TaskPlan:
        prompt = build_planner_prompt(user_request)
        response = await self._llm.generate(prompt)
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

    async def maybe_plan(self, session: SessionState, turn: TurnState) -> dict | None:
        if not self.needs_planning(turn.user_message):
            return None
        plan = await self.generate_plan(turn.user_message)
        return plan.model_dump()

    async def replan(
        self,
        session: SessionState,
        turn: TurnState,
    ) -> dict:
        plan_data = session.current_plan
        if not plan_data:
            return await self.generate_plan(turn.user_message).model_dump()

        completed = [
            s.get("title", "") for s in plan_data.get("steps", [])
            if s.get("status") == "done"
        ]
        failed_step = "unknown"
        for s in plan_data.get("steps", []):
            if s.get("status") not in ("done", "pending"):
                failed_step = s.get("title", "unknown")
                break

        reason = turn.current_action.get("reason", "Agent requested replan") if turn.current_action else "Agent requested replan"

        prompt = build_replan_prompt(turn.user_message, failed_step, reason, completed)
        response = await self._llm.generate(prompt)
        data = extract_json_from_text(response)

        if data is None:
            return plan_data

        try:
            new_plan = TaskPlan(
                goal=data.get("goal", turn.user_message),
                steps=[
                    PlanStep(
                        id=s.get("id", str(i + 1)),
                        title=s["title"],
                        description=s.get("description", s["title"]),
                        status="pending",
                    )
                    for i, s in enumerate(data.get("steps", []))
                ],
                version=plan_data.get("version", 1) + 1,
                summary=data.get("summary"),
            )
            return new_plan.model_dump()
        except (KeyError, TypeError):
            return plan_data

    def _fallback_plan(self, user_request: str) -> TaskPlan:
        return TaskPlan(
            goal=user_request,
            steps=[PlanStep(id="1", title="Complete the task", description=user_request)],
            summary="Single-step fallback plan",
        )
