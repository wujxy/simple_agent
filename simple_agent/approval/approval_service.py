from __future__ import annotations

from simple_agent.approval.approval_store import ApprovalRequest, ApprovalStore
from simple_agent.utils.ids import generate_id


class ApprovalService:
    def __init__(self, store: ApprovalStore) -> None:
        self._store = store

    async def create_request(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        args: dict,
        description: str | None,
        message: str | None = None,
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            request_id=generate_id("apr"),
            session_id=session_id,
            turn_id=turn_id,
            tool_name=tool_name,
            args=args,
            description=description,
            status="pending",
            message=message,
        )
        self._store.add(req)
        return req

    async def approve(self, request_id: str) -> ApprovalRequest:
        self._store.update_status(request_id, "approved")
        return self._store.get(request_id)

    async def deny(self, request_id: str) -> ApprovalRequest:
        self._store.update_status(request_id, "denied")
        return self._store.get(request_id)

    async def get(self, request_id: str) -> ApprovalRequest | None:
        return self._store.get(request_id)
