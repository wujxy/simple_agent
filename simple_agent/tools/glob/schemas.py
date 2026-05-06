from __future__ import annotations

from pydantic import BaseModel, Field


class GlobInput(BaseModel):
    pattern: str
    root: str = "."
    max_results: int = Field(default=200, ge=1, le=1000)
