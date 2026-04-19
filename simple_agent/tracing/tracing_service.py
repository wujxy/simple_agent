from __future__ import annotations

import time

from simple_agent.utils.logging_utils import get_logger

logger = get_logger("tracing")


class TracingService:
    def start_span(self, name: str, session_id: str, turn_id: str | None = None) -> dict:
        span = {
            "name": name,
            "session_id": session_id,
            "turn_id": turn_id,
            "start_time": time.time(),
        }
        logger.info("Span started: %s session=%s turn=%s", name, session_id, turn_id)
        return span

    def end_span(self, span: dict, metadata: dict | None = None) -> None:
        elapsed = time.time() - span.get("start_time", time.time())
        logger.info(
            "Span ended: %s duration=%.2fs %s",
            span.get("name", "unknown"),
            elapsed,
            f"metadata={metadata}" if metadata else "",
        )

    def log_event(self, name: str, payload: dict) -> None:
        logger.info("Event: %s %s", name, payload)
