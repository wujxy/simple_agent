from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCapabilities(BaseModel):
    read_only: bool = False
    idempotent: bool = False
    mutates_files: bool = False
    requires_approval: bool = False
    preferred_after_write: bool = False
    returns_high_value_payload: bool = False


class ToolSpec(BaseModel):
    name: str
    description: str
    family: Literal["filesystem", "shell", "other"]
    capabilities: ToolCapabilities = Field(default_factory=ToolCapabilities)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    guarantees: list[str] = Field(default_factory=list)
    short_prompt: str = ""
    detail_prompt: str = ""


class ToolObservation(BaseModel):
    ok: bool = True
    status: Literal["success", "noop", "unchanged", "error", "approval_required", "context_required"] = "success"
    summary: str = ""
    facts: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retryable: bool = False
    changed_paths: list[str] = Field(default_factory=list)


class ToolCallRecord(BaseModel):
    turn_id: str
    tool: str
    args: dict[str, Any]
    result: ToolObservation


class ApprovalGrant(BaseModel):
    session_id: str
    turn_id: str
    tool: str
    scope: Literal["request", "turn", "task", "file"]
    file_path: str | None = None
    granted: bool = True
