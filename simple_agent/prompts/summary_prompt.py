from __future__ import annotations


def build_summary_prompt(user_request: str, actions_summary: str) -> str:
    return f"""You are a summarization agent. Provide a concise final summary.

Original task: {user_request}

What was done:
{actions_summary}

CRITICAL INSTRUCTIONS:
1. Respond with ONLY valid JSON
2. Start with {{ and end with }}

Required JSON format:
{{
  "summary": "concise summary of what was accomplished",
  "outputs": ["list of key outputs or results"],
  "issues": ["any unresolved issues, or empty list if none"]
}}

Response (JSON only):"""
