from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApprovalRequest:
    request_id: str
    session_id: str
    turn_id: str
    tool_name: str
    args: dict = field(default_factory=dict)
    description: str | None = None
    status: str = "pending"  # pending | approved | denied | expired
    message: str | None = None


class ApprovalStore:
    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}

    def add(self, req: ApprovalRequest) -> None:
        self._requests[req.request_id] = req

    def get(self, request_id: str) -> ApprovalRequest | None:
        return self._requests.get(request_id)

    def update_status(self, request_id: str, status: str) -> None:
        req = self._requests.get(request_id)
        if req:
            req.status = status
