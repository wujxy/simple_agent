from __future__ import annotations

import uuid

from simple_agent.schemas import RunState, TaskPlan


VALID_TRANSITIONS: dict[str, set[str]] = {
    "created": {"planning", "running", "aborted"},
    "planning": {"running", "failed", "aborted"},
    "waiting_approval": {"running", "aborted"},
    "running": {"waiting_approval", "verifying", "failed", "aborted"},
    "verifying": {"running", "completed", "failed"},
    "completed": set(),
    "failed": set(),
    "aborted": set(),
}


class StateManager:
    def __init__(self, user_request: str, max_steps: int = 20) -> None:
        self._state = RunState(
            run_id=uuid.uuid4().hex[:8],
            user_request=user_request,
            max_steps=max_steps,
        )

    @property
    def state(self) -> RunState:
        return self._state

    def transition(self, new_status: str) -> None:
        current = self._state.status
        if new_status not in VALID_TRANSITIONS.get(current, set()):
            raise ValueError(f"Invalid transition: {current} -> {new_status}")
        self._state.status = new_status

    def set_plan(self, plan: TaskPlan) -> None:
        self._state.plan = plan

    def increment_step(self) -> None:
        self._state.step_count += 1

    def set_current_step(self, step_id: str | None) -> None:
        self._state.current_step_id = step_id

    def is_terminal(self) -> bool:
        return self._state.status in ("completed", "failed", "aborted")

    def over_step_limit(self) -> bool:
        return self._state.step_count >= self._state.max_steps
