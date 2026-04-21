from __future__ import annotations

from simple_agent.context.context_layers import PromptContext
from simple_agent.engine.query_state import QueryState
from simple_agent.prompts.action_prompt import (
    assemble_prompt,
    build_capability_prompt,
    build_context_prompt,
    build_system_core,
)
from simple_agent.prompts.planner_prompt import build_planner_prompt, build_replan_prompt
from simple_agent.prompts.summary_prompt import build_summary_prompt
from simple_agent.prompts.verify_prompt import build_verify_prompt
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("prompt_service")


class PromptService:
    def build_action_prompt(
        self,
        state: QueryState,
        prompt_context: PromptContext,
        tool_descriptions: str,
        *,
        include_batch: bool = False,
    ) -> str:
        system_core = build_system_core()
        rules = ""
        capabilities = build_capability_prompt(tool_descriptions, include_batch=include_batch)
        plan_progress = self._format_plan_progress(state.current_plan)
        context = build_context_prompt(prompt_context, plan_progress=plan_progress)
        user_input = self._format_current_input(state)

        # Debug: log each layer's size
        logger.info(
            "PROMPT LAYERS (step %d): system_core=%d chars, rules=%d chars, "
            "capabilities=%d chars, context=%d chars, user_input=%d chars, total=%d chars",
            state.step_count,
            len(system_core), len(rules), len(capabilities),
            len(context), len(user_input),
            len(system_core) + len(rules) + len(capabilities) + len(context) + len(user_input),
        )
        logger.debug("PROMPT FULL (step %d):\n%s", state.step_count,
                     assemble_prompt(system_core, rules, capabilities, context, user_input))

        return assemble_prompt(
            system_core=system_core,
            rules=rules,
            capabilities=capabilities,
            context=context,
            user_input=user_input,
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

    def build_summary_prompt(self, state: QueryState, context) -> str:
        if hasattr(context, "compact_memory_summary"):
            return build_summary_prompt(state.user_message, context.compact_memory_summary)
        return build_summary_prompt(state.user_message, "(no prior context)")

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

    def _format_current_input(self, state: QueryState) -> str:
        parts = [f"User task: {state.user_message}"]
        if state.current_plan:
            summary = state.current_plan.get("summary")
            if summary:
                parts.append(f"Current plan: {summary}")
            for step in state.current_plan.get("steps", []):
                if step.get("status") == "pending":
                    title = step.get("title", "")
                    desc = step.get("description", "")
                    parts.append(f"Current step: {title}: {desc}")
                    break
        return "\n".join(parts)
