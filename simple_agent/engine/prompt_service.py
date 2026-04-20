from __future__ import annotations

from simple_agent.engine.query_state import QueryState
from simple_agent.prompts.action_prompt import build_action_prompt
from simple_agent.prompts.planner_prompt import build_planner_prompt, build_replan_prompt
from simple_agent.prompts.summary_prompt import build_summary_prompt
from simple_agent.prompts.verify_prompt import build_verify_prompt


class PromptService:
    def build_action_prompt(
        self,
        state: QueryState,
        context: dict,
        tool_descriptions: str,
    ) -> str:
        memory_items = context.get("important_memory", [])
        memory_context = self._format_memory(memory_items) if memory_items else "(no prior context)"

        plan_summary = None
        if state.current_plan:
            plan_summary = state.current_plan.get("summary")

        current_step = None
        if state.current_plan and state.current_plan.get("steps"):
            for step in state.current_plan["steps"]:
                if step.get("status") == "pending":
                    current_step = f"{step.get('title', '')}: {step.get('description', '')}"
                    break

        return build_action_prompt(
            user_request=state.user_message,
            tool_descriptions=tool_descriptions,
            memory_context=memory_context,
            plan_summary=plan_summary,
            current_step=current_step,
            state_mode=state.mode,
        )

    def build_planning_prompt(self, state: QueryState) -> str:
        return build_planner_prompt(state.user_message)

    def build_replanning_prompt(
        self,
        state: QueryState,
        failed_step: str,
        reason: str,
        completed_steps: list[str],
    ) -> str:
        return build_replan_prompt(state.user_message, failed_step, reason, completed_steps)

    def build_verification_prompt(self, state: QueryState) -> str:
        actions_summary = state.last_summary or "(no prior context)"
        return build_verify_prompt(state.user_message, actions_summary)

    def build_summary_prompt(self, state: QueryState, context: dict) -> str:
        memory_items = context.get("important_memory", [])
        actions_summary = self._format_memory(memory_items)
        return build_summary_prompt(state.user_message, actions_summary)

    def _format_memory(self, items: list[dict]) -> str:
        if not items:
            return "(no prior context)"
        lines: list[str] = []
        for item in items:
            role = item.get("role", "unknown")
            content = item.get("content", item.get("output", ""))
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)
