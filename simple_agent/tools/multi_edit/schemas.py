from __future__ import annotations

from pydantic import BaseModel, Field


class EditOperation(BaseModel):
    old_text: str
    new_text: str
    replace_all: bool = False


class MultiEditInput(BaseModel):
    path: str
    edits: list[EditOperation] = Field(min_length=1)
