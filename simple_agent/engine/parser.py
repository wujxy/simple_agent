from __future__ import annotations

from simple_agent.schemas import AgentAction
from simple_agent.utils.json_utils import extract_json_from_text


class ParseError(Exception):
    pass


class ActionParser:
    def parse(self, llm_output: str) -> AgentAction:
        data = extract_json_from_text(llm_output)
        if data is None:
            raise ParseError("Could not extract valid JSON from LLM output")

        if not isinstance(data, dict):
            raise ParseError("LLM output is not a JSON object")

        if "type" not in data:
            raise ParseError("Missing required field: 'type'")

        action_type = data["type"]

        valid_types = {"tool_call", "plan", "replan", "verify", "summarize", "ask_user", "finish"}
        if action_type not in valid_types:
            raise ParseError(f"Unknown action type: '{action_type}'")

        if action_type == "tool_call" and not data.get("tool"):
            raise ParseError("tool_call action requires 'tool' field")
        if action_type in ("ask_user", "finish") and not data.get("message"):
            raise ParseError(f"{action_type} action requires 'message' field")

        return AgentAction(
            type=action_type,
            reason=data.get("reason", ""),
            tool=data.get("tool"),
            args=data.get("args", data.get("arguments", {})),
            message=data.get("message"),
        )

    def safe_parse(self, llm_output: str) -> AgentAction | None:
        try:
            return self.parse(llm_output)
        except ParseError:
            return None
