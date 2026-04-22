from __future__ import annotations

from pydantic import BaseModel, Field


class ReadFileInput(BaseModel):
    path: str
    start_line: int = Field(default=1, ge=1)
    max_lines: int | None = Field(default=None, ge=1)
