from __future__ import annotations

from pydantic import BaseModel, Field


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
    success: bool
    tool: str
    args: dict = Field(default_factory=dict)
    output: str | None = None
    error: str | None = None
    metadata: dict = Field(default_factory=dict)


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
