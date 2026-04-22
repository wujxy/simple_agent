from __future__ import annotations

from simple_agent.context.context_layers import PromptContext
from simple_agent.scheduler.task_scheduler import BATCHABLE_TOOLS
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


def build_capability_prompt(
    tool_descriptions: str,
    *,
    include_batch: bool = False,
) -> str:
    batch_section = ""
    if include_batch:
        batch_section = f"""

IMPORTANT — Batch parallel reads:
- When you need to read multiple files, ALWAYS use tool_batch to read them in ONE step.
- NEVER call read_file or list_dir one at a time when you need multiple files.
- tool_batch counts as a single step and returns all results at once.
- Only these tools support batch: {', '.join(sorted(BATCHABLE_TOOLS))}
- Write tools (write_file, bash) must still use single tool_call.

tool_batch JSON format:
{{"type": "tool_batch", "reason": "reading N files to understand the project", "actions": [{{"tool": "read_file", "args": {{"path": "file1.py"}}}}, {{"tool": "read_file", "args": {{"path": "file2.py"}}}}]}}

Example workflow:
Step 1: list_dir to discover files
Step 2: tool_batch to read ALL relevant files at once
Step 3: write_file to produce output"""

    return f"""Available tools:
{tool_descriptions}

Available actions:
- tool_call: Use a tool. JSON: {{"type": "tool_call", "reason": "why", "tool": "tool_name", "args": {{...}}}}
- tool_batch: Read multiple files in parallel. JSON: {{"type": "tool_batch", "reason": "why", "actions": [{{"tool": "...", "args": {{...}}}}, ...]}}
- plan: Create a plan. JSON: {{"type": "plan", "reason": "why planning is needed"}}
- replan: Request a new plan. JSON: {{"type": "replan", "reason": "why the plan needs changing"}}
- verify: Check if complete. JSON: {{"type": "verify", "reason": "why checking completion"}}
- summarize: Summarize progress. JSON: {{"type": "summarize", "reason": "why summarizing"}}
- ask_user: Ask for clarification. JSON: {{"type": "ask_user", "reason": "why", "message": "your question"}}
- finish: Task complete. JSON: {{"type": "finish", "reason": "why done", "message": "summary"}}{batch_section}

Planning policy:
Planning is optional, not mandatory. Choose `plan` only when it will improve execution quality.
Plan when: multi-file task, unclear project state, complex dependencies.
Skip plan when: small clear task, can implement and verify immediately."""


def build_context_prompt(prompt_context: PromptContext) -> str:
    """Build the context section from the 5 structured blocks."""
    blocks: list[str] = []

    # Block 1: Objective
    if prompt_context.objective_block:
        blocks.append(prompt_context.objective_block)

    # Block 2: Execution state
    if prompt_context.execution_state:
        blocks.append(f"Execution state:\n{prompt_context.execution_state}")

    # Block 3: Artifact snapshots
    if prompt_context.artifact_snapshot:
        blocks.append(prompt_context.artifact_snapshot)

    # Block 4: Confirmed facts
    if prompt_context.confirmed_facts:
        blocks.append(f"Confirmed facts:\n{prompt_context.confirmed_facts}")

    # Block 5: Next decision point
    if prompt_context.next_decision_point:
        blocks.append(prompt_context.next_decision_point)

    # Legacy: working set
    if prompt_context.working_set_summary:
        blocks.append(f"Working set:\n{prompt_context.working_set_summary}")

    # Legacy: recent observations
    if prompt_context.recent_observations:
        blocks.append(f"Recent observations:\n{prompt_context.recent_observations}")

    # Legacy: compact summary (last, lowest priority)
    if prompt_context.compact_memory_summary:
        blocks.append(f"Context summary:\n{prompt_context.compact_memory_summary}")

    return "\n\n".join(blocks)


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
