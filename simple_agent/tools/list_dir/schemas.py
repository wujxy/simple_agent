from __future__ import annotations

from pydantic import BaseModel


class ListDirInput(BaseModel):
    path: str
