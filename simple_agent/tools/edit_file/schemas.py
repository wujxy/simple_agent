from __future__ import annotations

from pydantic import BaseModel


class EditFileInput(BaseModel):
    path: str
    old_text: str
    new_text: str
    replace_all: bool = False
