from __future__ import annotations

from simple_agent.schemas import AgentAction
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

        parsed_args = data.get("args", data.get("arguments", {}))

        if action_type == "tool_call" and not data.get("tool"):
            raise ParseError("tool_call action requires 'tool' field")
        if action_type == "tool_batch":
            if "actions" not in data or not isinstance(data["actions"], list):
                raise ParseError("tool_batch requires 'actions' list field")
            args = parsed_args if isinstance(parsed_args, dict) else {}
            args_actions_before = len(args.get("actions", []))
            parsed_args = {**args, "actions": data["actions"]}
            logger.info(
                "[BATCH_DEBUG] parser tool_batch: top_level_actions=%d "
                "args_actions_before=%d returned_actions=%d data_keys=%s args_keys=%s",
                len(data["actions"]),
                args_actions_before,
                len(parsed_args["actions"]),
                sorted(data.keys()),
                sorted(parsed_args.keys()),
            )
        if action_type in ("ask_user", "finish") and not data.get("message"):
            raise ParseError(f"{action_type} action requires 'message' field")

        return AgentAction(
            type=action_type,
            reason=data.get("reason", ""),
            tool=data.get("tool"),
            args=parsed_args,
            message=data.get("message"),
        )

    def safe_parse(self, llm_output: str) -> AgentAction | None:
        try:
            return self.parse(llm_output)
        except ParseError:
            return None
