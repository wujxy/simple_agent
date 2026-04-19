from __future__ import annotations


def build_verify_prompt(user_request: str, actions_summary: str) -> str:
    return f"""You are a verification agent. Determine whether the task has been completed.

Original task: {user_request}

Actions taken and results:
{actions_summary}

CRITICAL INSTRUCTIONS:
1. Respond with ONLY valid JSON
2. Start with {{ and end with }}

Required JSON format:
{{
  "complete": true/false,
  "reason": "why you think it is or isn't complete",
  "missing": "what's still missing, or null if complete"
}}

Response (JSON only):"""
