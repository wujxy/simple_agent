from __future__ import annotations

from simple_agent.context.context_layers import PromptContext

# --- Layer 1: System Core ---

SYSTEM_CORE = """You are a precise AI agent that executes tasks step by step.

Behavioral rules:
1. Respond with ONLY valid JSON — no explanations, no markdown, no extra text
2. Start with {{ and end with }}
3. Choose exactly ONE action per turn
4. Use tools when you need information or to perform actions
5. Do NOT repeat a tool call that already succeeded (check Plan progress)
6. After writing a file, do NOT re-read it — the diff in the tool result shows what was written
7. Use verify/finish when you believe the task is complete
8. Ask the user if you are stuck or need clarification"""


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

    return f"""Current state:
{prompt_context.query_state_projection}
{progress_section}
Working set:
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
