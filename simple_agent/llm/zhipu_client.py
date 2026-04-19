from __future__ import annotations

import asyncio
import os
from typing import AsyncIterator

from zhipuai import ZhipuAI

from simple_agent.utils.logging_utils import get_logger

logger = get_logger("llm.zhipu")


class ZhipuClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "glm-4.7",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout: int = 60,
        max_retries: int = 3,
    ) -> None:
        key = api_key or os.environ.get("ZHIPU_API_KEY", "")
        if not key:
            raise ValueError("ZHIPU_API_KEY not set. Set env var or pass api_key.")

        self._client = ZhipuAI(api_key=key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries = max_retries

    async def complete(self, prompt: str, **kwargs) -> str:
        return await self.complete_with_messages([{"role": "user", "content": prompt}], **kwargs)

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        messages = [{"role": "user", "content": prompt}]
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            top_p=0.7,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    async def complete_with_messages(self, messages: list[dict], **kwargs) -> str:
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    top_p=0.7,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                last_error = e
                logger.warning("LLM call failed (attempt %d/%d): %s", attempt + 1, self._max_retries, e)
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"All {self._max_retries} LLM calls failed: {last_error}")
