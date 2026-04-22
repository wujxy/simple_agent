from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from simple_agent.tools.core.types import ToolObservation, ToolSpec


class BaseTool(ABC):
    spec: ToolSpec
    input_model: type[BaseModel]

    @abstractmethod
    async def run(self, tool_input: BaseModel, ctx: dict | None = None) -> ToolObservation: ...

    async def validate(self, tool_input: BaseModel, ctx: dict | None = None) -> ToolObservation | None:
        return None

    async def check_preconditions(self, tool_input: BaseModel, ctx: dict | None = None) -> ToolObservation | None:
        return None
