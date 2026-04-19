from __future__ import annotations

from collections import defaultdict
from typing import Callable

from simple_agent.runtime.event_types import Event
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("event_bus")


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        logger.info(
            "Event: type=%s source=%s session=%s turn=%s",
            event.type,
            event.source,
            event.session_id,
            event.turn_id,
        )
        for handler in self._handlers.get(event.type, []):
            await handler(event)
