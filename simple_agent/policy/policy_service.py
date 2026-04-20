from __future__ import annotations

from pathlib import Path

import yaml

from simple_agent.hooks.pre_tool_use import ToolInvocation
from simple_agent.policy.policy_engine import PolicyEngine
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("policy_service")


class PolicyService:
    """Backward-compatible wrapper around PolicyEngine."""

    def __init__(self, config: dict | None = None, config_path: str | None = None) -> None:
        merged_config: dict = {}
        if config:
            merged_config.update(config)
        if config_path:
            p = Path(config_path)
            if p.exists():
                with open(p) as f:
                    data = yaml.safe_load(f) or {}
                merged_config.update(data)
        self._engine = PolicyEngine(merged_config)

    @property
    def engine(self) -> PolicyEngine:
        return self._engine

    async def check(self, tool_name: str, args: dict) -> dict:
        inv = ToolInvocation(session_id="", turn_id="", tool_name=tool_name, args=args)
        decision = await self._engine.evaluate(inv)
        return {"status": decision.status, "reason": decision.reason}
