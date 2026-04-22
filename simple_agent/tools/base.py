from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from simple_agent.schemas import ToolOutput


class ToolSpec(BaseModel):
    name: str
    description: str
    args_schema: dict


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def args_schema(self) -> dict: ...

    @abstractmethod
    async def run(self, **kwargs) -> ToolOutput: ...

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            args_schema=self.args_schema,
        )
