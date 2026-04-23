from __future__ import annotations

from simple_agent.runtime.event_bus import EventBus
from simple_agent.sessions.session_store import SessionStore
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("session_service")


class SessionService:
    def __init__(self, store: SessionStore, event_bus: EventBus | None = None) -> None:
        self._store = store
        self._event_bus = event_bus

    async def create_session(self, cwd: str | None = None) -> dict:
        session = self._store.create_session(cwd)
        logger.info("Session created: %s", session.session_id)
        return {"session_id": session.session_id, "status": session.status}

    async def get_session(self, session_id: str) -> dict | None:
        session = self._store.get_session(session_id)
        if session is None:
            return None
        return {
            "session_id": session.session_id,
            "status": session.status,
            "cwd": session.cwd,
            "active_turn_id": session.active_turn_id,
        }

    async def mark_waiting_user(self, session_id: str, turn_id: str, message: str) -> None:
        session = self._store.get_session(session_id)
        if session:
            session.status = "waiting_user"
            session.active_turn_id = turn_id
            self._store.save_session(session)

    async def close_turn(self, session_id: str, turn_id: str, status: str) -> None:
        turn = self._store.get_turn(turn_id)
        if turn:
            turn.status = status
            self._store.save_turn(turn)
        session = self._store.get_session(session_id)
        if session and session.active_turn_id == turn_id:
            session.active_turn_id = None
            session.status = "active"
            self._store.save_session(session)
