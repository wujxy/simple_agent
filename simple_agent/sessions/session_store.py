from __future__ import annotations

from simple_agent.sessions.schemas import SessionState, TurnState
from simple_agent.utils.ids import gen_session_id, gen_turn_id


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._turns: dict[str, TurnState] = {}

    def create_session(self, cwd: str | None = None) -> SessionState:
        import time

        session = SessionState(
            session_id=gen_session_id(),
            created_at=time.time(),
            cwd=cwd,
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def save_session(self, session: SessionState) -> None:
        self._sessions[session.session_id] = session

    def create_turn(
        self, session_id: str, user_message: str, max_steps: int = 20
    ) -> TurnState:
        import time

        turn = TurnState(
            turn_id=gen_turn_id(),
            session_id=session_id,
            user_message=user_message,
            max_steps=max_steps,
            started_at=time.time(),
        )
        self._turns[turn.turn_id] = turn
        return turn

    def get_turn(self, turn_id: str) -> TurnState | None:
        return self._turns.get(turn_id)

    def save_turn(self, turn: TurnState) -> None:
        self._turns[turn.turn_id] = turn
