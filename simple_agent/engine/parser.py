from __future__ import annotations

from pydantic import TypeAdapter, ValidationError

from simple_agent.schemas import ParsedAgentAction
from simple_agent.utils.json_utils import extract_json_from_text
from simple_agent.utils.logging_utils import get_logger


logger = get_logger("parser")


class ParseError(Exception):
    pass


# Known tool names that should be auto-converted to tool_call
_KNOWN_TOOLS = {
    "read_file",
    "write_file",
    "bash",
    "list_dir",
    "glob",
    "grep",
    "edit_file",
    "multi_edit",
}

_VALID_TYPES = {"tool_call", "tool_batch", "plan", "replan", "verify", "summarize", "ask_user", "finish"}
_ACTION_ADAPTER = TypeAdapter(ParsedAgentAction)


class ActionParser:
    def parse(self, llm_output: str) -> ParsedAgentAction:
        data = extract_json_from_text(llm_output)
        if data is None:
            raise ParseError("Could not extract valid JSON from LLM output")

        if not isinstance(data, dict):
            raise ParseError("LLM output is not a JSON object")

        if "type" not in data:
            raise ParseError("Missing required field: 'type'")

        action_type = data["type"]

        # Auto-convert: if the LLM used a tool name as the action type, wrap it as tool_call
        if action_type in _KNOWN_TOOLS:
            data = {
                "type": "tool_call",
                "reason": data.get("reason", ""),
                "tool": action_type,
                "args": data.get("args", {}),
            }
            action_type = "tool_call"

        if action_type not in _VALID_TYPES:
            raise ParseError(f"Unknown action type: '{action_type}'")

        if action_type == "tool_call":
            if not data.get("tool"):
                raise ParseError("tool_call action requires 'tool' field")
            if "args" not in data and "arguments" in data:
                data["args"] = data["arguments"]

        if action_type == "tool_batch":
            legacy_args = data.get("args", data.get("arguments", {}))
            if "actions" not in data and isinstance(legacy_args, dict) and "actions" in legacy_args:
                data["actions"] = legacy_args["actions"]
            if "actions" not in data or not isinstance(data["actions"], list):
                raise ParseError("tool_batch requires 'actions' list field")
            if not data["actions"]:
                raise ParseError("tool_batch requires at least one action")
            for idx, item in enumerate(data["actions"]):
                if not isinstance(item, dict):
                    raise ParseError(f"tool_batch action {idx} must be an object")
                if not item.get("tool"):
                    raise ParseError(f"tool_batch action {idx} requires 'tool'")

        if action_type in ("ask_user", "finish") and not data.get("message"):
            raise ParseError(f"{action_type} action requires 'message' field")

        try:
            return _ACTION_ADAPTER.validate_python(data)
        except ValidationError as e:
            logger.warning("Action protocol validation failed: %s", e)
            raise ParseError(f"Action protocol validation failed: {e}") from e

    def safe_parse(self, llm_output: str) -> ParsedAgentAction | None:
        try:
            return self.parse(llm_output)
        except ParseError:
            return None
