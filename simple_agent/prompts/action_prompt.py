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
    run_mode: str = "normal",
    mode_policy: dict | None = None,
) -> str:
    mode_policy = mode_policy or {}
    mode_section = f"""Runtime mode: {run_mode}
Policy:
- read tools: {'allowed' if mode_policy.get('allow_read', True) else 'disabled'}
- write tools: {'allowed' if mode_policy.get('allow_write') else 'require approval' if mode_policy.get('require_approval_for_write', True) else 'disabled'}
- bash: {'allowed' if mode_policy.get('allow_bash') else 'require approval' if mode_policy.get('require_approval_for_bash', True) else 'disabled'}
- planning: {'required for complex tasks' if mode_policy.get('planning_required') else 'optional'}
- finish verification: {'strict' if mode_policy.get('strict_verify') else 'standard'}
- hard limits: max tool calls {mode_policy.get('max_tool_calls', 80)}, max writes {mode_policy.get('max_writes', 20)}
"""
    batch_section = ""
    if include_batch:
        batch_section = f"""

IMPORTANT — Batch parallel reads:
- When you already know a group of relevant files to read, use ONE tool_batch for that group.
- NEVER call read_file or list_dir one at a time for files that are already known in the same decision.
- tool_batch counts as a single step and returns all results at once.
- Only these tools support batch: {', '.join(sorted(BATCHABLE_TOOLS))}
- Empty tool_batch actions are invalid.
- Write tools (write_file, bash) must still use single tool_call.

tool_batch JSON format:
{{"type": "tool_batch", "reason": "reading N files to understand the project", "actions": [{{"tool": "read_file", "args": {{"path": "file1.py"}}}}, {{"tool": "read_file", "args": {{"path": "file2.py"}}}}]}}

Example workflow:
Step 1: list_dir to discover files
Step 2: tool_batch to read all selected relevant files for this step
Step 3: write_file to produce output"""

    planning_policy = {
        "plan": "Complex tasks require a plan; maintain plan progress and replan when blocked.",
        "yolo": "Act autonomously within hard boundaries. Still verify before finish when files changed or commands ran.",
    }.get(run_mode, "Planning is optional, not mandatory. Choose `plan` only when it will improve execution quality.")

    return f"""{mode_section}

Available tools:
{tool_descriptions}

Available actions:
- tool_call: Use a tool. JSON: {{"type": "tool_call", "reason": "why", "tool": "tool_name", "args": {{...}}}}
- tool_batch: Read one or more known read-only targets in parallel. JSON: {{"type": "tool_batch", "reason": "why", "actions": [{{"tool": "...", "args": {{...}}}}, ...]}}
- plan: Create a plan. JSON: {{"type": "plan", "reason": "why planning is needed"}}
- replan: Request a new plan. JSON: {{"type": "replan", "reason": "why the plan needs changing"}}
- verify: Check if complete. JSON: {{"type": "verify", "reason": "why checking completion"}}
- summarize: Summarize progress. JSON: {{"type": "summarize", "reason": "why summarizing"}}
- ask_user: Ask for clarification. JSON: {{"type": "ask_user", "reason": "why", "message": "your question"}}
- finish: Task complete. JSON: {{"type": "finish", "reason": "why done", "message": "summary"}}{batch_section}

Planning policy:
{planning_policy}
Plan when: multi-file task, unclear project state, complex dependencies.
Skip plan when: small clear task, can implement and verify immediately."""


def build_context_prompt(prompt_context: PromptContext) -> str:
    """Build the context section from structured blocks."""
    blocks: list[str] = []

    # Block 0: Project rules / long-term instructions
    if prompt_context.project_rules_block:
        blocks.append(f"Project rules:\n{prompt_context.project_rules_block}")

    # Block 1: Objective
    if prompt_context.objective_block:
        blocks.append(prompt_context.objective_block)

    # Block 2: Execution state
    if prompt_context.execution_state:
        blocks.append(f"Execution state:\n{prompt_context.execution_state}")

    # Block 3: Prompt memory
    if prompt_context.prompt_memory_block:
        blocks.append(f"Memory:\n{prompt_context.prompt_memory_block}")

    # Block 4: Working set
    if prompt_context.working_set_block:
        blocks.append(prompt_context.working_set_block)

    # Block 5: Artifact snapshots
    if prompt_context.artifact_snapshot:
        blocks.append(prompt_context.artifact_snapshot)

    # Block 6: Next decision point
    if prompt_context.next_decision_point:
        blocks.append(prompt_context.next_decision_point)

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
