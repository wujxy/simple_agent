from __future__ import annotations

from simple_agent.context.context_layers import PromptContext
from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.prompt_builder import (
    build_code_task_rules_prompt,
    build_tool_contracts_prompt,
    build_tool_protocol_prompt,
    build_trust_rules_prompt,
)


def build_system_core() -> str:
    return build_tool_protocol_prompt()


def build_trust_rules() -> str:
    return build_trust_rules_prompt()


def build_tool_contracts(tools: list[BaseTool]) -> str:
    return build_tool_contracts_prompt(tools)


def build_code_task_rules() -> str:
    return build_code_task_rules_prompt()


BATCHABLE_TOOLS = {"read_file", "list_dir"}


def build_capability_prompt(
    tool_descriptions: str,
    *,
    include_batch: bool = False,
) -> str:
    batch_section = ""
    if include_batch:
        batch_section = f"""

Batch tool calls:
- For reading multiple files or listing multiple directories at once, use tool_batch
- JSON: {{"type": "tool_batch", "reason": "why", "actions": [{{"tool": "...", "args": {{...}}}}, ...]}}
- Only these tools support batch: {', '.join(sorted(BATCHABLE_TOOLS))}
- Write tools (write_file, bash) must still use single tool_call"""

    return f"""Available tools:
{tool_descriptions}

Available actions:
- tool_call: Use a tool. JSON: {{"type": "tool_call", "reason": "why", "tool": "tool_name", "args": {{...}}}}
- plan: Create a plan. JSON: {{"type": "plan", "reason": "why planning is needed"}}
- replan: Request a new plan. JSON: {{"type": "replan", "reason": "why the plan needs changing"}}
- verify: Check if complete. JSON: {{"type": "verify", "reason": "why checking completion"}}
- summarize: Summarize progress. JSON: {{"type": "summarize", "reason": "why summarizing"}}
- ask_user: Ask for clarification. JSON: {{"type": "ask_user", "reason": "why", "message": "your question"}}
- finish: Task complete. JSON: {{"type": "finish", "reason": "why done", "message": "summary"}}{batch_section}"""


def build_context_prompt(prompt_context: PromptContext, plan_progress: str = "") -> str:
    progress_section = ""
    if plan_progress:
        progress_section = f"\nPlan progress:\n{plan_progress}\n"

    facts_section = ""
    if prompt_context.confirmed_facts:
        facts_section = f"\nConfirmed facts:\n{prompt_context.confirmed_facts}\n"

    snapshots_section = ""
    if prompt_context.working_snapshots:
        snapshots_section = f"\nWorking file snapshots:\n{prompt_context.working_snapshots}\n"

    shell_section = ""
    if prompt_context.recent_shell_results:
        shell_section = f"\nRecent shell results:\n{prompt_context.recent_shell_results}\n"

    return f"""Current state:
{prompt_context.query_state_projection}
{progress_section}{facts_section}{snapshots_section}{shell_section}Working set:
{prompt_context.working_set_summary}

Recent observations:
{prompt_context.recent_observations}

Context summary:
{prompt_context.compact_memory_summary}"""


def assemble_prompt(
    system_core: str,
    trust_rules: str,
    tool_contracts: str,
    code_task_rules: str,
    capabilities: str,
    context: str,
    user_input: str,
    project_rules: str = "",
) -> str:
    rules_section = f"\n\nProject rules:\n{project_rules}" if project_rules else ""

    return f"""{system_core}

{trust_rules}

{tool_contracts}

{code_task_rules}

{capabilities}

{context}{rules_section}

{user_input}

Response (JSON only):"""
