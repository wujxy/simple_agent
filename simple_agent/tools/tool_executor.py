from __future__ import annotations

from simple_agent.policy.policy_service import PolicyService
from simple_agent.schemas import ToolResult
from simple_agent.tools.registry import ToolRegistry
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("tool_executor")


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, policy_service: PolicyService) -> None:
        self._registry = registry
        self._policy = policy_service

    async def execute(self, session_id: str, turn_id: str, tool_name: str, args: dict) -> ToolResult:
        decision = await self._policy.check(tool_name, args)
        status = decision["status"]

        if status == "deny":
            reason = decision["reason"]
            logger.warning("Policy denied: %s", reason)
            return ToolResult(success=False, tool=tool_name, args=args, error=reason)

        if status == "ask":
            reason = decision["reason"]
            logger.info("Approval required: %s — auto-approving in v1", reason)

        tool = self._registry.get(tool_name)
        if tool is None:
            return ToolResult(success=False, tool=tool_name, args=args, error=f"Unknown tool: '{tool_name}'")

        try:
            output = await tool.run(**args)
            return ToolResult(success=True, tool=tool_name, args=args, output=output)
        except Exception as e:
            return ToolResult(success=False, tool=tool_name, args=args, error=str(e))
