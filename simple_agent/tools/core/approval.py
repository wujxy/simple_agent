from __future__ import annotations

from simple_agent.tools.core.types import ApprovalGrant


class ApprovalMemory:
    def __init__(self) -> None:
        self._grants: list[ApprovalGrant] = []

    def record(self, grant: ApprovalGrant) -> None:
        self._grants.append(grant)

    def is_approved(
        self,
        session_id: str,
        turn_id: str,
        tool: str,
        file_path: str | None = None,
    ) -> bool:
        """Check if a tool was already approved in this turn scope."""
        for grant in reversed(self._grants):
            if grant.session_id != session_id:
                continue
            if grant.scope == "turn" and grant.turn_id == turn_id and grant.tool == tool:
                return True
            if grant.scope == "file" and grant.turn_id == turn_id and grant.file_path == file_path:
                return True
        return False

    def clear_session(self, session_id: str) -> None:
        self._grants = [g for g in self._grants if g.session_id != session_id]
