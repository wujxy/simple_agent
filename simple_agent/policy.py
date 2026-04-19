from __future__ import annotations

from pathlib import Path

import yaml

from simple_agent.schemas import AgentAction, PolicyDecision


class PolicyChecker:
    def __init__(self, config_path: str | None = None) -> None:
        self._rules: dict = {
            "allow_read": True,
            "allow_write": False,
            "allow_bash": False,
            "allow_network": False,
            "require_approval_for_write": True,
            "require_approval_for_bash": True,
            "blocked_commands": ["rm -rf", "mkfs", "dd", "format"],
        }
        if config_path:
            self._load_config(config_path)

    def _load_config(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f) or {}
            self._rules.update(data)

    def check(self, action: AgentAction) -> PolicyDecision:
        if action.type != "tool_call":
            return PolicyDecision(allowed=True, reason="Non-tool action allowed")

        tool = action.tool or ""
        tool_policy = {
            "read_file": "allow_read",
            "list_dir": "allow_read",
            "write_file": "allow_write",
            "bash": "allow_bash",
        }

        rule_key = tool_policy.get(tool)
        if rule_key is None:
            return PolicyDecision(allowed=True, reason=f"No policy restriction for '{tool}'")

        if not self._rules.get(rule_key, False):
            approval_key = f"require_approval_for_{rule_key.replace('allow_', '')}"
            if self._rules.get(approval_key, False):
                return PolicyDecision(
                    allowed=True,
                    requires_approval=True,
                    reason=f"Tool '{tool}' requires user approval",
                )
            return PolicyDecision(allowed=False, reason=f"Tool '{tool}' is disabled by policy")

        # Extra check for blocked shell commands
        if tool == "bash":
            command = action.args.get("command", "")
            for blocked in self._rules.get("blocked_commands", []):
                if blocked in command:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Blocked command pattern: '{blocked}'",
                    )

        return PolicyDecision(allowed=True, reason=f"Tool '{tool}' allowed")
