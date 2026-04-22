from __future__ import annotations

from pydantic import BaseModel, Field


class WriteFileInput(BaseModel):
    path: str
    content: str
