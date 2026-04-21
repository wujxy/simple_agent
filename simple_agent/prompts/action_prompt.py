from __future__ import annotations

from simple_agent.context.context_layers import PromptContext

# --- Layer 1: System Core ---

SYSTEM_CORE = """You are a precise AI agent that executes tasks step by step.

Behavioral rules:
1. Respond with ONLY valid JSON — no explanations, no markdown, no extra text.
2. Start with {{ and end with }}
3. Choose the single best next action for this turn.
4. Treat successful tool results as facts — do not re-verify them.
5. If write_file succeeds, the file now exactly matches the content you supplied.
6. Do not re-read a file you just wrote unless you need a specific verification not already available.
7. Before requesting another write, check whether the current file already satisfies the remaining subgoals.
8. Prefer verify, summarize, or finish over repeated writes when the code likely already covers the requirements.
9. Do not repeat an identical successful tool call without a new reason.
10. Ask the user only if you are blocked by missing information or an approval decision."""


def build_system_core() -> str:
    return SYSTEM_CORE


# --- Layer 3: Capabilities ---

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


# --- Layer 4: Context ---

def build_context_prompt(prompt_context: PromptContext, plan_progress: str = "") -> str:
    progress_section = ""
    if plan_progress:
        progress_section = f"\nPlan progress:\n{plan_progress}\n"

    facts_section = ""
    if prompt_context.confirmed_facts:
        facts_section = f"\nConfirmed facts:\n{prompt_context.confirmed_facts}\n"

    return f"""Current state:
{prompt_context.query_state_projection}
{progress_section}{facts_section}Working set:
{prompt_context.working_set_summary}

Recent observations:
{prompt_context.recent_observations}

Context summary:
{prompt_context.compact_memory_summary}"""


# --- Assembly ---

def assemble_prompt(
    system_core: str,
    rules: str,
    capabilities: str,
    context: str,
    user_input: str,
) -> str:
    rules_section = f"\n\nProject rules:\n{rules}" if rules else ""

    return f"""{system_core}{rules_section}

{capabilities}

{context}

{user_input}

Response (JSON only):"""
