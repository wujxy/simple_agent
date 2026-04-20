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

        last_result_str = self._format_last_tool_result(context.get("last_tool_result"))
        plan_progress = self._format_plan_progress(state.current_plan)

        return build_action_prompt(
            user_request=state.user_message,
            tool_descriptions=tool_descriptions,
            memory_context=memory_context,
            plan_summary=plan_summary,
            current_step=current_step,
            state_mode=state.mode,
            last_tool_result_str=last_result_str,
            plan_progress=plan_progress,
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

    def _format_last_tool_result(self, result: dict | None) -> str:
        if not result:
            return ""
        tool = result.get("tool_name", "?")
        success = result.get("success", False)
        output = result.get("output", "")
        error = result.get("error", "")
        if success:
            return f"Last tool result: {tool} succeeded -> {output[:300]}"
        return f"Last tool result: {tool} failed -> {error[:300]}"

    def _format_plan_progress(self, plan: dict | None) -> str:
        if not plan or not plan.get("steps"):
            return ""
        lines: list[str] = []
        for i, step in enumerate(plan["steps"], 1):
            status = step.get("status", "pending")
            title = step.get("title", f"Step {i}")
            if status == "done":
                notes = step.get("notes", "")
                note_str = f" -> {notes[:100]}" if notes else ""
                lines.append(f"  [done] {title}{note_str}")
            elif status == "failed":
                lines.append(f"  [failed] {title}")
            else:
                lines.append(f"  [pending] {title}")
        return "\n".join(lines)
