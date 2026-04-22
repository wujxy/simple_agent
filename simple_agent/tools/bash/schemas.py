from __future__ import annotations

from pydantic import BaseModel, Field


class BashInput(BaseModel):
    command: str
    timeout: int = Field(default=30, ge=1, le=300)
