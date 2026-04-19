from __future__ import annotations

import uuid


def gen_session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"


def gen_turn_id() -> str:
    return f"turn_{uuid.uuid4().hex[:12]}"


def gen_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"
