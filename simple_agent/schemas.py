from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from simple_agent.tools.core.types import ToolObservation


class PlanStep(BaseModel):
    id: str
    title: str
    description: str
    status: str = "pending"  # pending | running | done | failed | skipped
    notes: str | None = None


class TaskPlan(BaseModel):
    goal: str
    steps: list[PlanStep]
    version: int = 1
    summary: str | None = None


class AgentAction(BaseModel):
    type: str  # tool_call | ask_user | replan | finish
    reason: str = ""
    tool: str | None = None
    args: dict = Field(default_factory=dict)
    message: str | None = None


class ToolResult(BaseModel):
    observation: ToolObservation
    tool: str
    args: dict = Field(default_factory=dict)

    # Approval fields
    approval_required: bool = False
    approval_request_id: str | None = None
    approval_message: str | None = None


class PolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str = ""


class RunState(BaseModel):
    run_id: str
    user_request: str
    status: str = "created"  # created | planning | waiting_approval | running | verifying | completed | failed | aborted
    step_count: int = 0
    max_steps: int = 20
    current_step_id: str | None = None
    plan: TaskPlan | None = None


class ExecutionPlanStep(BaseModel):
    step_id: str
    title: str
    purpose: str = ""
    action_type: Literal["inspect", "read", "modify", "run", "verify", "finalize"] = "inspect"
    target_files: list[str] = Field(default_factory=list)
    entry_conditions: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    status: str = "pending"  # pending | candidate_done | done | failed | blocked | skipped
    notes: str | None = None


class ExecutionPlan(BaseModel):
    overview: str
    deliverables: list[str] = Field(default_factory=list)
    likely_files: list[str] = Field(default_factory=list)
    verification_targets: list[str] = Field(default_factory=list)
    steps: list[ExecutionPlanStep] = Field(default_factory=list)
