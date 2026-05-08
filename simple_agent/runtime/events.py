from __future__ import annotations

import time

from simple_agent.runtime.event_bus import EventBus
from simple_agent.runtime.event_types import Event
from simple_agent.utils.ids import gen_event_id


async def publish_runtime_event(
    event_bus: EventBus | None,
    event_type: str,
    *,
    session_id: str,
    source: str,
    payload: dict | None = None,
    turn_id: str | None = None,
    step: int | None = None,
) -> None:
    if event_bus is None:
        return
    event_payload = dict(payload or {})
    if step is not None:
        event_payload.setdefault("step", step)
    await event_bus.publish(Event(
        event_id=gen_event_id(),
        session_id=session_id,
        turn_id=turn_id,
        type=event_type,
        source=source,
        payload=event_payload,
        ts=time.time(),
    ))
