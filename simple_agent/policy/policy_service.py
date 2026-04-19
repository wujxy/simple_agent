from __future__ import annotations

from pathlib import Path

import yaml

from simple_agent.utils.logging_utils import get_logger

logger = get_logger("policy_service")


class PolicyService:
    def __init__(self, config: dict | None = None, config_path: str | None = None) -> None:
        self._rules: dict = {
            "allow_read": True,
            "allow_write": False,
            "allow_bash": False,
            "require_approval_for_write": True,
            "require_approval_for_bash": True,
            "blocked_commands": ["rm -rf", "mkfs", "dd", "format"],
        }
        if config:
            self._rules.update(config)
        if config_path:
            self._load_config(config_path)

    def _load_config(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f) or {}
            self._rules.update(data)

    async def check(self, tool_name: str, args: dict) -> dict:
        tool_policy = {
            "read_file": "allow_read",
            "list_dir": "allow_read",
            "write_file": "allow_write",
            "bash": "allow_bash",
        }

        rule_key = tool_policy.get(tool_name)
        if rule_key is None:
            return {"status": "allow", "reason": f"No policy restriction for '{tool_name}'"}

        if not self._rules.get(rule_key, False):
            approval_key = f"require_approval_for_{rule_key.replace('allow_', '')}"
            if self._rules.get(approval_key, False):
                return {"status": "ask", "reason": f"Tool '{tool_name}' requires user approval"}
            return {"status": "deny", "reason": f"Tool '{tool_name}' is disabled by policy"}

        if tool_name == "bash":
            command = args.get("command", "")
            for blocked in self._rules.get("blocked_commands", []):
                if blocked in command:
                    return {"status": "deny", "reason": f"Blocked command pattern: '{blocked}'"}

        return {"status": "allow", "reason": f"Tool '{tool_name}' allowed"}
