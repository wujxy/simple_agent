from __future__ import annotations

from simple_agent.approval.approval_store import ApprovalRequest


class CLIApprovalAdapter:
    def format_prompt(self, req: ApprovalRequest) -> str:
        desc = f"\nDescription: {req.description}" if req.description else ""
        return (
            f"Tool '{req.tool_name}' requires approval.{desc}\n"
            f"Args: {req.args}\n"
            "Type '/approve' or 'y' to approve, anything else to deny."
        )
