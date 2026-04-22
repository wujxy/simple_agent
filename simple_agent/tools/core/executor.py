from __future__ import annotations

from simple_agent.approval.approval_service import ApprovalService
from simple_agent.hooks.hook_manager import HookManager
from simple_agent.hooks.pre_tool_use import ToolInvocation
from simple_agent.schemas import ToolResult
from simple_agent.tools.core.approval import ApprovalMemory
from simple_agent.tools.core.registry import ToolRegistry
from simple_agent.tools.core.types import ToolObservation
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("tool_executor")


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        hook_manager: HookManager,
        approval_service: ApprovalService,
        approval_memory: ApprovalMemory | None = None,
    ) -> None:
        self._registry = registry
        self._hook_manager = hook_manager
        self._approval_service = approval_service
        self._approval_memory = approval_memory or ApprovalMemory()

    async def execute(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        args: dict,
        *,
        approved: bool = False,
    ) -> ToolResult:
        # Check if already approved in this turn via ApprovalMemory
        if not approved and self._approval_memory.is_approved(
            session_id, turn_id, tool_name, args.get("path")
        ):
            logger.info("Approval already granted in this turn for %s", tool_name)
            approved = True

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
                return ToolResult(
                    observation=ToolObservation(ok=False, status="error", error=reason, summary=reason),
                    tool=tool_name, args=args,
                )

            if decision.status == "context_required":
                msg = decision.message or "Context required"
                logger.info("Context required: %s", msg)
                return ToolResult(
                    observation=ToolObservation(ok=False, status="context_required", error=msg, summary=msg),
                    tool=tool_name, args=args,
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
                    observation=ToolObservation(
                        ok=False, status="approval_required",
                        summary=reason, error=reason,
                    ),
                    tool=tool_name, args=args,
                    approval_required=True,
                    approval_request_id=req.request_id,
                    approval_message=decision.message or reason,
                )

        tool = self._registry.get(tool_name)
        if tool is None:
            return ToolResult(
                observation=ToolObservation(ok=False, status="error", error=f"Unknown tool: '{tool_name}'"),
                tool=tool_name, args=args,
            )

        try:
            input_model = tool.input_model(**args)
        except Exception as e:
            return ToolResult(
                observation=ToolObservation(ok=False, status="error", error=f"Invalid input: {e}"),
                tool=tool_name, args=args,
            )

        try:
            obs: ToolObservation = await tool.run(input_model)
        except Exception as e:
            logger.error("Tool %s raised exception: %s", tool_name, e)
            return ToolResult(
                observation=ToolObservation(ok=False, status="error", error=str(e), retryable=True),
                tool=tool_name, args=args,
            )

        return ToolResult(observation=obs, tool=tool_name, args=args)
