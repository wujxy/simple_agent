from __future__ import annotations


def build_planner_prompt(user_request: str) -> str:
    return f"""You are a planning agent. Create a concise, actionable plan for the user's task.

CRITICAL INSTRUCTIONS:
1. Respond with ONLY valid JSON
2. No explanations before or after the JSON
3. Start with {{ and end with }}

Required JSON format:
{{
  "goal": "clear restatement of the task",
  "steps": [
    {{"id": "1", "title": "step title", "description": "what to do"}},
    ...
  ],
  "summary": "one-line plan summary"
}}

Rules:
- Keep steps small and specific
- 2-6 steps is usually enough
- If the task is trivial (single action), use 1 step
- Each step should be independently executable

User task: {user_request}

Response (JSON only):"""


def build_replan_prompt(user_request: str, failed_step: str, reason: str, completed_steps: list[str]) -> str:
    completed = "\n".join(f"- {s}" for s in completed_steps) if completed_steps else "(none)"
    return f"""You are a planning agent. The previous plan hit a blocker and needs adjustment.

Original task: {user_request}

Completed steps:
{completed}

Failed step: {failed_step}
Failure reason: {reason}

Create a revised plan starting from where things went wrong.

CRITICAL INSTRUCTIONS:
1. Respond with ONLY valid JSON
2. No explanations before or after the JSON
3. Start with {{ and end with }}

Required JSON format:
{{
  "goal": "updated goal if needed",
  "steps": [
    {{"id": "1", "title": "step title", "description": "what to do"}},
    ...
  ],
  "summary": "revised plan summary"
}}

Response (JSON only):"""
