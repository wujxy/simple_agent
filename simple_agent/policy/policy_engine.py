from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from simple_agent.hooks.pre_tool_use import HookDecision, PreToolUseHook, ToolInvocation
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("policy_engine")


@dataclass
class PolicyDecision:
    status: str  # allow | deny | ask | context_required
    reason: str | None = None
    approval_message: str | None = None


class PolicyEngine:
    TOOL_RULE_MAP: dict[str, str] = {
        "read_file": "allow_read",
        "list_dir": "allow_read",
        "write_file": "allow_write",
        "bash": "allow_bash",
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._rules: dict[str, Any] = {
            "allow_read": True,
            "allow_write": False,
            "allow_bash": False,
            "require_approval_for_write": True,
            "require_approval_for_bash": True,
            "blocked_commands": ["rm -rf", "mkfs", "dd", "format"],
        }
        if config:
            self._rules.update(config)

    async def evaluate(self, invocation: ToolInvocation) -> PolicyDecision:
        rule_key = self.TOOL_RULE_MAP.get(invocation.tool_name)
        if rule_key is None:
            return PolicyDecision(status="allow", reason=f"No policy for '{invocation.tool_name}'")

        if not self._rules.get(rule_key, False):
            approval_key = f"require_approval_for_{rule_key.replace('allow_', '')}"
            if self._rules.get(approval_key, False):
                msg = f"Tool '{invocation.tool_name}' requires approval. Type '/approve' or 'y' to approve, anything else to deny."
                return PolicyDecision(
                    status="ask",
                    reason=f"Tool '{invocation.tool_name}' requires user approval",
                    approval_message=msg,
                )
            return PolicyDecision(status="deny", reason=f"Tool '{invocation.tool_name}' is disabled by policy")

        if invocation.tool_name == "bash":
            command = invocation.args.get("command", "")
            for blocked in self._rules.get("blocked_commands", []):
                if blocked in command:
                    return PolicyDecision(status="deny", reason=f"Blocked command pattern: '{blocked}'")

        return PolicyDecision(status="allow", reason=f"Tool '{invocation.tool_name}' allowed")


class PolicyHook(PreToolUseHook):
    def __init__(self, engine: PolicyEngine) -> None:
        self._engine = engine

    async def before_tool_use(self, invocation: ToolInvocation) -> HookDecision:
        decision = await self._engine.evaluate(invocation)
        return HookDecision(
            status=decision.status,
            reason=decision.reason,
            message=decision.approval_message,
        )
