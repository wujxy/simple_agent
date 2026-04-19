from __future__ import annotations

from typing import AsyncIterator

from simple_agent.llm.base import BaseLLMClient
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("llm_service")


class LLMService:
    def __init__(self, client: BaseLLMClient, config: dict | None = None) -> None:
        self._client = client
        self._config = config or {}

    async def generate(self, prompt: str) -> str:
        logger.info("LLM generate request (%d chars)", len(prompt))
        try:
            result = await self._client.complete(prompt)
            logger.info("LLM generate response (%d chars)", len(result))
            return result
        except Exception as e:
            logger.error("LLM generate failed: %s", e)
            raise

    async def generate_with_messages(self, messages: list[dict]) -> str:
        logger.info("LLM generate_with_messages (%d messages)", len(messages))
        try:
            result = await self._client.complete_with_messages(messages)
            logger.info("LLM generate_with_messages response (%d chars)", len(result))
            return result
        except Exception as e:
            logger.error("LLM generate_with_messages failed: %s", e)
            raise

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        logger.info("LLM stream request (%d chars)", len(prompt))
        async for chunk in self._client.stream(prompt):
            yield chunk
