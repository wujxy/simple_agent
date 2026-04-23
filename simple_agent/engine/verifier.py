from __future__ import annotations

from simple_agent.engine.query_state import QueryState
from simple_agent.llm.llm_service import LLMService
from simple_agent.prompts.verify_prompt import build_verify_prompt
from simple_agent.sessions.schemas import SessionState
from simple_agent.utils.json_utils import extract_json_from_text
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("verifier")


class Verifier:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def verify(self, session: SessionState, state: QueryState, context: dict) -> dict:
        evidence = self._format_context(context)
        prompt = build_verify_prompt(state.user_message, evidence)

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

    def _format_context(self, context) -> str:
        if hasattr(context, "artifact_snapshot"):
            parts = []
            if context.objective_block:
                parts.append(f"=== Objective ===\n{context.objective_block}")
            if context.execution_state:
                parts.append(f"=== Execution State ===\n{context.execution_state}")
            if context.prompt_memory_block:
                parts.append(f"=== Memory ===\n{context.prompt_memory_block}")
            if context.artifact_snapshot:
                parts.append(f"=== Artifact Evidence ===\n{context.artifact_snapshot}")
            return "\n\n".join(parts) if parts else "(no prior context)"

        if isinstance(context, dict):
            memory_items = context.get("important_memory", [])
            if not memory_items:
                return "(no prior context)"
            lines: list[str] = []
            for item in memory_items:
                role = item.get("role", "unknown")
                content = item.get("content", item.get("output", ""))
                lines.append(f"[{role}] {content}")
            return "\n".join(lines)
        return "(no prior context)"
