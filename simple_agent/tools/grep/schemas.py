from __future__ import annotations

from pydantic import BaseModel, Field


class GrepInput(BaseModel):
    pattern: str
    root: str = "."
    include: str = "**/*"
    max_results: int = Field(default=100, ge=1, le=1000)
    case_sensitive: bool = True
