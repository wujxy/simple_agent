from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunMode(str, Enum):
    NORMAL = "normal"
    PLAN = "plan"
    YOLO = "yolo"


class RunStatus(str, Enum):
    RUNNING = "running"
    WAITING_USER_INPUT = "waiting_user_input"
    WAITING_USER_APPROVAL = "waiting_user_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ModePolicy(BaseModel):
    allow_read: bool = True
    allow_write: bool = False
    allow_bash: bool = False
    require_approval_for_write: bool = True
    require_approval_for_bash: bool = True
    planning_required: bool = False
    strict_verify: bool = False
    max_steps: int = 20
    max_tool_calls: int = 80
    max_writes: int = 20
    max_runtime_seconds: int | None = None
    blocked_commands: list[str] = Field(default_factory=lambda: ["rm -rf", "mkfs", "dd", "format"])


class ModeDecision(BaseModel):
    status: str  # allow | deny | ask | context_required
    reason: str
    approval_message: str | None = None
    run_mode: str = RunMode.NORMAL.value
    policy: dict[str, Any] = Field(default_factory=dict)


@dataclass
class TurnModeUsage:
    run_mode: RunMode
    started_at: float = field(default_factory=time.time)
    tool_calls: int = 0
    writes: int = 0


READ_TOOLS = {"read_file", "list_dir", "glob", "grep"}
WRITE_TOOLS = {"write_file", "edit_file", "multi_edit"}
BASH_TOOLS = {"bash"}


class ModeService:
    """Runtime mode policy and turn-scoped hard-limit accounting."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._runtime_config = self._config.get("runtime", {})
        self._policy_config = self._config.get("policy", {})
        self._mode_config = self._config.get("modes", {})
        self._turn_usage: dict[tuple[str, str], TurnModeUsage] = {}

    def normalize_mode(self, value: str | RunMode | None) -> RunMode:
        try:
            return RunMode((value or self.default_mode()).value if isinstance(value, RunMode) else (value or self.default_mode()))
        except ValueError:
            return RunMode.NORMAL

    def default_mode(self) -> str:
        return str(self._runtime_config.get("run_mode") or self._runtime_config.get("mode") or RunMode.NORMAL.value)

    def policy_for_mode(self, run_mode: str | RunMode | None) -> ModePolicy:
        mode = self.normalize_mode(run_mode)
        max_steps = int(self._runtime_config.get("max_steps", 20))
        blocked = list(self._policy_config.get("blocked_commands", ["rm -rf", "mkfs", "dd", "format"]))
        common = {
            "max_steps": max_steps,
            "max_tool_calls": int(self._runtime_config.get("max_tool_calls", 80)),
            "max_writes": int(self._runtime_config.get("max_writes", 20)),
            "max_runtime_seconds": self._runtime_config.get("max_runtime_seconds"),
            "blocked_commands": blocked,
        }

        if mode == RunMode.PLAN:
            policy = ModePolicy(
                allow_read=True,
                allow_write=False,
                allow_bash=False,
                require_approval_for_write=True,
                require_approval_for_bash=True,
                planning_required=True,
                strict_verify=True,
                **common,
            )
        elif mode == RunMode.YOLO:
            policy = ModePolicy(
                allow_read=True,
                allow_write=True,
                allow_bash=True,
                require_approval_for_write=False,
                require_approval_for_bash=False,
                planning_required=False,
                strict_verify=True,
                **common,
            )
        else:
            policy = ModePolicy(
                allow_read=True,
                allow_write=False,
                allow_bash=False,
                require_approval_for_write=True,
                require_approval_for_bash=True,
                planning_required=False,
                strict_verify=False,
                **common,
            )

        overrides = self._mode_config.get(mode.value, {})
        if overrides:
            policy = policy.model_copy(update=overrides)
        return policy

    def start_turn(self, session_id: str, turn_id: str, run_mode: str | RunMode | None) -> RunMode:
        mode = self.normalize_mode(run_mode)
        key = (session_id, turn_id)
        if key in self._turn_usage:
            self._turn_usage[key].run_mode = mode
        else:
            self._turn_usage[key] = TurnModeUsage(run_mode=mode)
        return mode

    def get_turn_mode(self, session_id: str, turn_id: str, fallback: str | RunMode | None = None) -> RunMode:
        usage = self._turn_usage.get((session_id, turn_id))
        if usage:
            return usage.run_mode
        return self.normalize_mode(fallback)

    def usage_snapshot(self, session_id: str, turn_id: str) -> dict[str, Any]:
        usage = self._turn_usage.get((session_id, turn_id))
        if not usage:
            return {"tool_calls": 0, "writes": 0, "elapsed_seconds": 0}
        return {
            "tool_calls": usage.tool_calls,
            "writes": usage.writes,
            "elapsed_seconds": int(time.time() - usage.started_at),
        }

    def evaluate_tool_boundary(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        args: dict[str, Any],
        *,
        run_mode: str | RunMode | None = None,
        approved: bool = False,
    ) -> ModeDecision:
        mode = self.get_turn_mode(session_id, turn_id, run_mode)
        policy = self.policy_for_mode(mode)
        usage = self._turn_usage.setdefault((session_id, turn_id), TurnModeUsage(run_mode=mode))

        if usage.tool_calls >= policy.max_tool_calls:
            return self._deny(mode, policy, f"Mode limit exceeded: max_tool_calls={policy.max_tool_calls}")
        if tool_name in WRITE_TOOLS and usage.writes >= policy.max_writes:
            return self._deny(mode, policy, f"Mode limit exceeded: max_writes={policy.max_writes}")
        if policy.max_runtime_seconds is not None and (time.time() - usage.started_at) >= policy.max_runtime_seconds:
            return self._deny(mode, policy, f"Mode limit exceeded: max_runtime_seconds={policy.max_runtime_seconds}")

        if tool_name == "bash":
            command = str(args.get("command", ""))
            for blocked in policy.blocked_commands:
                if blocked and blocked in command:
                    return self._deny(mode, policy, f"Blocked command pattern: '{blocked}'")

        if tool_name in READ_TOOLS:
            return self._allow(mode, policy, f"Tool '{tool_name}' allowed by {mode.value} mode")
        if tool_name in WRITE_TOOLS:
            if policy.allow_write:
                return self._allow(mode, policy, f"Tool '{tool_name}' allowed by {mode.value} mode")
            if policy.require_approval_for_write and not approved:
                return self._ask(mode, policy, tool_name)
            if policy.require_approval_for_write and approved:
                return self._allow(mode, policy, f"Tool '{tool_name}' approved by user")
            return self._deny(mode, policy, f"Tool '{tool_name}' is disabled by {mode.value} mode")
        if tool_name in BASH_TOOLS:
            if policy.allow_bash:
                return self._allow(mode, policy, f"Tool '{tool_name}' allowed by {mode.value} mode")
            if policy.require_approval_for_bash and not approved:
                return self._ask(mode, policy, tool_name)
            if policy.require_approval_for_bash and approved:
                return self._allow(mode, policy, f"Tool '{tool_name}' approved by user")
            return self._deny(mode, policy, f"Tool '{tool_name}' is disabled by {mode.value} mode")

        return self._allow(mode, policy, f"No mode policy for '{tool_name}'")

    def record_tool_started(self, session_id: str, turn_id: str, tool_name: str) -> None:
        usage = self._turn_usage.setdefault(
            (session_id, turn_id),
            TurnModeUsage(run_mode=self.get_turn_mode(session_id, turn_id)),
        )
        usage.tool_calls += 1
        if tool_name in WRITE_TOOLS:
            usage.writes += 1

    def _allow(self, mode: RunMode, policy: ModePolicy, reason: str) -> ModeDecision:
        return ModeDecision(status="allow", reason=reason, run_mode=mode.value, policy=policy.model_dump())

    def _deny(self, mode: RunMode, policy: ModePolicy, reason: str) -> ModeDecision:
        return ModeDecision(status="deny", reason=reason, run_mode=mode.value, policy=policy.model_dump())

    def _ask(self, mode: RunMode, policy: ModePolicy, tool_name: str) -> ModeDecision:
        msg = f"Tool '{tool_name}' requires approval in {mode.value} mode. Type '/approve' or 'y' to approve, anything else to deny."
        return ModeDecision(
            status="ask",
            reason=f"Tool '{tool_name}' requires user approval in {mode.value} mode",
            approval_message=msg,
            run_mode=mode.value,
            policy=policy.model_dump(),
        )
