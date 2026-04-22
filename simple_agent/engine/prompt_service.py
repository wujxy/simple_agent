from __future__ import annotations

from simple_agent.context.context_layers import PromptContext
from simple_agent.engine.query_state import QueryState
from simple_agent.prompts.action_prompt import (
    assemble_prompt,
    build_capability_prompt,
    build_code_task_rules,
    build_context_prompt,
    build_system_core,
    build_tool_contracts,
    build_trust_rules,
)
from simple_agent.prompts.planner_prompt import build_planner_prompt, build_replan_prompt
from simple_agent.prompts.summary_prompt import build_summary_prompt
from simple_agent.prompts.verify_prompt import build_verify_prompt
from simple_agent.tools.core.base import BaseTool
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("prompt_service")


class PromptService:
    def __init__(self, tools: list[BaseTool] | None = None) -> None:
        self._tools = tools or []

    def set_tools(self, tools: list[BaseTool]) -> None:
        self._tools = tools

    def build_action_prompt(
        self,
        state: QueryState,
        prompt_context: PromptContext,
        tool_descriptions: str,
        *,
        include_batch: bool = False,
    ) -> str:
        system_core = build_system_core()
        trust_rules = build_trust_rules()
        tool_contracts = build_tool_contracts(self._tools)
        code_task_rules = build_code_task_rules()
        capabilities = build_capability_prompt(tool_descriptions, include_batch=include_batch)
        context = build_context_prompt(prompt_context)
        user_input = self._format_user_input(state)

        logger.info(
            "PROMPT LAYERS (step %d): core=%d, trust=%d, contracts=%d, "
            "code_rules=%d, capabilities=%d, context=%d, user_input=%d",
            state.step_count,
            len(system_core), len(trust_rules), len(tool_contracts),
            len(code_task_rules), len(capabilities), len(context), len(user_input),
        )

        return assemble_prompt(
            system_core=system_core,
            trust_rules=trust_rules,
            tool_contracts=tool_contracts,
            code_task_rules=code_task_rules,
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

    def _format_user_input(self, state: QueryState) -> str:
        return f"User task: {state.user_message}"
