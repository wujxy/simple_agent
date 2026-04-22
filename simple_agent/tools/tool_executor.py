from __future__ import annotations

from simple_agent.approval.approval_service import ApprovalService
from simple_agent.hooks.hook_manager import HookManager
from simple_agent.hooks.pre_tool_use import ToolInvocation
from simple_agent.schemas import ToolOutput, ToolResult
from simple_agent.tools.registry import ToolRegistry
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("tool_executor")


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        hook_manager: HookManager,
        approval_service: ApprovalService,
    ) -> None:
        self._registry = registry
        self._hook_manager = hook_manager
        self._approval_service = approval_service

    async def execute(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        args: dict,
        *,
        approved: bool = False,
    ) -> ToolResult:
        if not approved:
            invocation = ToolInvocation(
                session_id=session_id,
                turn_id=turn_id,
                tool_name=tool_name,
                args=args,
            )
            decision = await self._hook_manager.run_pre_tool_use(invocation)

            if decision.status == "deny":
                reason = decision.reason or "Denied by policy"
                logger.warning("Policy denied: %s", reason)
                return ToolResult(success=False, tool=tool_name, args=args, error=reason)

            if decision.status == "context_required":
                msg = decision.message or "Context required"
                logger.info("Context required: %s", msg)
                return ToolResult(
                    success=False, tool=tool_name, args=args, error=msg,
                    context_required=True, context_message=msg,
                )

            if decision.status == "ask":
                reason = decision.reason or "Requires approval"
                logger.info("Approval required: %s", reason)
                req = await self._approval_service.create_request(
                    session_id=session_id,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    args=args,
                    description=None,
                    message=decision.message,
                )
                return ToolResult(
                    success=False, tool=tool_name, args=args, error=reason,
                    approval_required=True,
                    approval_request_id=req.request_id,
                    approval_message=decision.message or reason,
                )

        tool = self._registry.get(tool_name)
        if tool is None:
            return ToolResult(success=False, tool=tool_name, args=args, error=f"Unknown tool: '{tool_name}'")

        try:
            output: ToolOutput = await tool.run(**args)
        except Exception as e:
            logger.error("Tool %s raised exception: %s", tool_name, e)
            return ToolResult(success=False, tool=tool_name, args=args, error=str(e))

        success = output.status == "success"

        # Determine what goes into the output field for prompt/display
        if "content" in output.data:
            display_output = output.data["content"]
        elif "stdout" in output.data:
            display_output = output.data["stdout"]
        else:
            display_output = output.summary

        return ToolResult(
            success=success,
            tool=tool_name,
            args=args,
            output=display_output or "",
            error=output.error if not success else None,
            summary=output.summary,
            facts=output.facts,
            metadata=output.data,
        )
