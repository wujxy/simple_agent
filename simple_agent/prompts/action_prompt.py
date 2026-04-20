from __future__ import annotations


def build_action_prompt(
    user_request: str,
    tool_descriptions: str,
    memory_context: str,
    plan_summary: str | None = None,
    current_step: str | None = None,
    state_mode: str = "running",
    last_tool_result_str: str = "",
    plan_progress: str = "",
) -> str:
    plan_section = ""
    if plan_summary:
        plan_section = f"\nCurrent plan: {plan_summary}"
    step_section = ""
    if current_step:
        step_section = f"\nCurrent step to work on: {current_step}"
    last_result_section = ""
    if last_tool_result_str:
        last_result_section = f"\n{last_tool_result_str}\n"
    progress_section = ""
    if plan_progress:
        progress_section = f"\nPlan progress:\n{plan_progress}\n"

    return f"""You are a precise AI agent. Decide exactly one next action.

User task: {user_request}{plan_section}{step_section}

Current state: {state_mode}
{progress_section}{last_result_section}
Recent context:
{memory_context}

Available tools:
{tool_descriptions}

CRITICAL INSTRUCTIONS:
1. Respond with ONLY valid JSON
2. No explanations, no markdown, no extra text
3. Start with {{ and end with }}

Available actions:
- tool_call: Use a tool. JSON: {{"type": "tool_call", "reason": "why", "tool": "tool_name", "args": {{...}}}}
- plan: Create a plan for the task. JSON: {{"type": "plan", "reason": "why planning is needed"}}
- replan: Request a new plan. JSON: {{"type": "replan", "reason": "why the plan needs changing"}}
- verify: Check if the task is complete. JSON: {{"type": "verify", "reason": "why checking completion"}}
- summarize: Summarize progress so far. JSON: {{"type": "summarize", "reason": "why summarizing"}}
- ask_user: Ask for clarification. JSON: {{"type": "ask_user", "reason": "why", "message": "your question"}}
- finish: Task is complete. JSON: {{"type": "finish", "reason": "why done", "message": "summary of what was accomplished"}}

Rules:
- Choose exactly ONE action
- Use tools when you need information or to perform actions
- Use plan for complex tasks that need decomposition
- Use verify when you think the task might be done
- Use summarize to consolidate progress on long tasks
- Finish only when the task is fully complete
- Ask the user if you are stuck or need clarification
- Do NOT repeat a tool call that already succeeded (check Plan progress above)

Response (JSON only):"""
