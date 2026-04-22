from __future__ import annotations

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolSpec


def build_tool_protocol_prompt() -> str:
    """Layer A — Shared Tool Protocol."""
    return """Tool protocol:
1. Every tool call returns a structured observation with: ok, status, summary, facts, data, error.
2. Status values: success | noop | unchanged | error | approval_required | context_required.
3. If ok=true, the tool succeeded. Trust the result — do not re-verify.
4. If status=noop, the operation was skipped because it would have no effect.
5. If status=unchanged, the resource has not changed since your last read.
6. If status=context_required, you lack the context to justify this action. Re-evaluate.
7. If status=approval_required, wait for user approval before proceeding."""


def build_trust_rules_prompt() -> str:
    """Layer B — Tool Result Trust Rules."""
    return """Trust rules:
- write_file success → the file now exactly matches the content you supplied. Do NOT re-read it.
- write_file noop → the file already had identical content. No action was needed.
- read_file success → data.content is the file text. Trust it.
- read_file unchanged → the file has not changed since last read. Use cached knowledge.
- bash success → exit_code=0, stdout/stderr contain full output.
- bash error → check exit_code and stderr for the failure reason.
- After a successful write, prefer bash (run tests) or verify over re-reading the file.
- Do NOT issue the same tool call with identical arguments twice in a row without new evidence."""


def build_tool_contracts_prompt(tools: list[BaseTool]) -> str:
    """Layer C — Core Tool Contracts (generated from each tool's spec)."""
    parts: list[str] = ["Tool contracts:"]
    for tool in tools:
        s: ToolSpec = tool.spec
        lines = [f"- {s.name}: {s.description}"]
        if s.short_prompt:
            lines.append(f"  Usage: {s.short_prompt}")
        if s.capabilities.read_only:
            lines.append("  Read-only: yes")
        if s.capabilities.requires_approval:
            lines.append("  Requires approval: yes")
        if s.capabilities.preferred_after_write:
            lines.append("  Preferred after write: yes (use this to verify instead of re-reading)")
        for g in s.guarantees:
            lines.append(f"  Guarantee: {g}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def build_code_task_rules_prompt() -> str:
    """Layer D — Code Task Continuation Rule."""
    return """Code task rules:
- Before writing code, ensure you have read all relevant source files first.
- After a successful write, prefer run/verify/finish over another write.
- A step moves to candidate_done when its tool succeeds. It moves to done only when evidence satisfies its completion criteria.
- Another write requires concrete evidence of a problem or gap (failed test, incomplete verification, new user requirement).
- A read_file that reveals a specific missing detail is valid evidence for a write. A read_file that just confirms what was written is not.
- Prefer finishing over perfecting — once all subgoals are met, use finish.
- If verification fails, analyze the error output and make targeted fixes — do not rewrite everything."""
