from __future__ import annotations

from simple_agent.llm.llm_service import LLMService
from simple_agent.prompts.verify_prompt import build_verify_prompt
from simple_agent.sessions.schemas import SessionState, TurnState
from simple_agent.utils.json_utils import extract_json_from_text
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("verifier")


class Verifier:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def verify(self, session: SessionState, turn: TurnState, context: dict) -> dict:
        actions_summary = self._format_context(context)
        prompt = build_verify_prompt(turn.user_message, actions_summary)

        try:
            response = await self._llm.generate(prompt)
            data = extract_json_from_text(response)

            if isinstance(data, dict):
                complete = data.get("complete", True)
                logger.info("Verification result: complete=%s", complete)
                return {
                    "complete": complete,
                    "reason": data.get("reason", ""),
                    "missing": data.get("missing", []),
                }

            logger.warning("Verification output could not be parsed")
            return {"complete": True, "reason": "Could not parse verification output", "missing": []}
        except Exception as e:
            logger.error("Verification failed: %s", e)
            return {"complete": True, "reason": f"Verification error: {e}", "missing": []}

    def _format_context(self, context: dict) -> str:
        memory_items = context.get("important_memory", [])
        if not memory_items:
            return "(no prior context)"
        lines: list[str] = []
        for item in memory_items:
            role = item.get("role", "unknown")
            content = item.get("content", item.get("output", ""))
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)
