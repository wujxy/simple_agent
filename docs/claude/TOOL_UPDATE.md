# TOOL_UPDATE.md

## Objective

Refactor the tool system so that the agent uses **strictly structured tool contracts**, preserves **full tool outputs** across turns, reduces unnecessary rewrites and approval loops, and makes planning/verification logic robust enough to continue work instead of falling back into `read -> write -> approval -> read` cycles.

This document is an **execution plan** for the implementer.

---

## Executive Summary

The current system already improved compared with the earliest version, but the agent still loops because the architecture is still only **pseudo-structured**, not **strongly structured**.

### Root causes

1. **Tool contract is still pseudo-structured**
   - Tools still fundamentally behave like `run() -> str` tools.
   - The executor heuristically parses JSON strings instead of enforcing a typed output model.
   - The contract is simulated in prompts, not enforced in runtime.

2. **Tool outputs are not preserved as first-class state**
   - `read_file` may read content, but the next prompt often only retains a summary such as line count.
   - `bash` and other tools must also preserve their original return payloads (`stdout`, `stderr`, `exit_code`, etc.) rather than only short summaries.
   - As a result, the model cannot reliably reason about what it already knows.

3. **Plan progression logic is too write-biased**
   - Pending subgoals are treated too literally.
   - The agent is pushed toward “write again” instead of first deciding whether the current implementation already satisfies the next subgoal.
   - Code-writing tasks should usually prefer `bash`/`verify` after a successful write, not `read_file` and not immediate rewrite.

4. **Approval is request-scoped, not context-scoped**
   - Repeated `write_file` calls within the same turn/task keep asking again.
   - Approval history must be remembered and reused under safe rules.

5. **Additional gaps**
   - No strong runtime guard prevents “write again without new evidence”.
   - Prompt and executor semantics are not fully aligned.
   - Tool-specific guarantees are not formally declared and enforced.

---

## Non-negotiable Design Principles

The refactor must follow these rules.

### 1. Strongly structured tools
A tool is **not allowed** to return free-form text as its primary contract.

Every tool must expose:
- a typed input model
- a typed output model
- capability metadata
- English prompt contract text
- runtime implementation

### 2. Single source of truth
Per-tool contract information must not be duplicated inconsistently across:
- prompt text
- executor logic
- tool implementation

Each tool folder must become the source of truth for:
- input schema
- output schema
- guarantees
- short prompt
- detail prompt

### 3. Full payload preservation
If a tool produces important output, the original output must be preserved in structured form.

Examples:
- `read_file` must preserve the actual content it read.
- `bash` must preserve `stdout`, `stderr`, `exit_code`, and related execution fields.
- Do **not** collapse high-value data into one-line summaries only.

### 4. Facts must be trustworthy and narrow
`facts` are not generic prose. They are **confirmed statements guaranteed by the tool**.

Examples:
- valid: `foo.py now exactly matches the supplied content.`
- valid: `The command 'pytest' exited with code 0.`
- invalid: `The task is complete.`
- invalid: `The code is correct.`

### 5. Prompt and runtime must agree
If the prompt says `write_file success means exact_match`, the runtime must enforce that.
If the runtime cannot guarantee something, it must not appear in prompt guarantees.

---

## Target Tool Directory Structure

Refactor tools into per-tool folders.

```text
simple_agent/tools/
  core/
    base.py
    types.py
    registry.py
    executor.py
    approval.py
    result_memory.py
  read_file/
    __init__.py
    schemas.py
    spec.py
    prompt.py
    tool.py
  write_file/
    __init__.py
    schemas.py
    spec.py
    prompt.py
    tool.py
  bash/
    __init__.py
    schemas.py
    spec.py
    prompt.py
    tool.py
  list_dir/
    __init__.py
    schemas.py
    spec.py
    prompt.py
    tool.py
```

### Notes
- `core/` holds shared abstractions only.
- Every real tool must live in its own folder.
- Do not leave hybrid legacy files in active execution paths after migration.

---

## Required Core Models

Create shared typed models in `simple_agent/tools/core/types.py`.

### Tool capability metadata

```python
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
    capabilities: ToolCapabilities
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    guarantees: list[str] = Field(default_factory=list)
    short_prompt: str
    detail_prompt: str
```

### Unified tool result model

```python
class ToolObservation(BaseModel):
    ok: bool
    status: Literal[
        "success",
        "noop",
        "unchanged",
        "error",
        "approval_required",
        "context_required",
    ]
    summary: str
    facts: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retryable: bool = False
    changed_paths: list[str] = Field(default_factory=list)
```

### Tool call envelope

```python
class ToolCallRecord(BaseModel):
    turn_id: str
    tool: str
    args: dict[str, Any]
    result: ToolObservation
```

---

## Required Core Base Interface

Replace legacy `run() -> str` behavior.

In `simple_agent/tools/core/base.py`, implement a generic base interface.

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from .types import ToolSpec, ToolObservation


class BaseTool(ABC):
    spec: ToolSpec
    input_model: type[BaseModel]

    @abstractmethod
    async def call(self, tool_input: BaseModel, ctx) -> ToolObservation:
        ...

    async def validate(self, tool_input: BaseModel, ctx) -> None:
        return None

    async def check_preconditions(self, tool_input: BaseModel, ctx) -> ToolObservation | None:
        return None
```

### Hard rule
- No active tool path is allowed to return a raw string as the tool contract.
- The executor must receive a validated `ToolObservation`, not a free-form string.

---

## Tool-by-Tool Contract Requirements

---

## `read_file`

### Input model

```python
class ReadFileInput(BaseModel):
    path: str
    start_line: int = 1
    max_lines: int | None = None
```

### Output requirements
The original content must be preserved.

```python
{
  "ok": true,
  "status": "success",
  "summary": "Read foo.py",
  "facts": ["Read lines 1-120 from foo.py."],
  "data": {
    "path": "foo.py",
    "content": "...actual file content...",
    "start_line": 1,
    "returned_lines": 120,
    "total_lines": 200,
    "truncated": true
  }
}
```

### `unchanged` semantics
If the exact same requested range was already read and has not changed since then, return:

```python
{
  "ok": true,
  "status": "unchanged",
  "summary": "foo.py unchanged since last read",
  "facts": ["The requested range of foo.py is unchanged since the previous read."],
  "data": {
    "path": "foo.py",
    "content": None,
    "unchanged": True
  }
}
```

### Mandatory guarantee
`read_file` detail prompt must explicitly say that successful reads preserve the original content in `data.content`.

---

## `write_file`

### Input model

```python
class WriteFileInput(BaseModel):
    path: str
    content: str
    create_dirs: bool = True
```

### Output requirements
Must guarantee exact file state on `success` and `noop`.

```python
{
  "ok": true,
  "status": "success",
  "summary": "Updated foo.py",
  "facts": ["foo.py now exactly matches the supplied content."],
  "data": {
    "path": "foo.py",
    "operation": "updated",
    "exact_match": true,
    "line_count": 57,
    "bytes_written": 1432
  },
  "changed_paths": ["foo.py"]
}
```

### `noop` semantics
If the file already matches the supplied content, return `noop`, not `success`.

### Hard runtime rule
`exact_match = true` is only allowed if the tool can actually guarantee it.

---

## `bash`

### Input model

```python
class BashInput(BaseModel):
    command: str
    timeout: int = 30
    cwd: str | None = None
```

### Output requirements
The original execution payload must be preserved.

```python
{
  "ok": true,
  "status": "success",
  "summary": "Ran pytest",
  "facts": ["The command 'pytest' exited with code 0."],
  "data": {
    "command": "pytest",
    "cwd": "/workspace",
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "timed_out": false
  }
}
```

### Hard rule
`bash success` only means command-level success, not task-level success.
Never claim task completion from `bash` alone.

---

## `list_dir`

### Output requirements
Must preserve original list data in structured form.

```python
{
  "ok": true,
  "status": "success",
  "summary": "Listed files in src/",
  "facts": ["Listed directory contents for src/."],
  "data": {
    "path": "src/",
    "entries": ["a.py", "b.py", "subdir/"]
  }
}
```

---

## Prompt Design Requirements (English Only)

All tool-related prompt text must be written in English.

### Prompt layer strategy
Because the current system only has core tools, core tool contracts can stay resident in prompt.
However, do **not** inject long manuals. Use a layered prompt.

### Layer A — Shared Tool Protocol (always present)

```text
All tools return a structured observation:
{ok, status, summary, facts, data, error, retryable, changed_paths}

Status meanings:
- success: the tool call completed and its facts may be treated as confirmed facts
- noop: the requested state was already true
- unchanged: the requested read target has not changed since the previous read
- error: the tool call failed
- approval_required: user approval is required before execution
- context_required: the call is blocked because more justification or new evidence is required
```

### Layer B — Tool Result Trust Rules (always present)

```text
Tool result trust rules:
1. Treat facts from success/noop/unchanged tool results as confirmed facts.
2. Do not infer conclusions beyond the tool's declared guarantees.
3. If write_file returns success or noop with data.exact_match=true, do not re-read the file unless:
   - the user explicitly asks for verification, or
   - another tool may have changed the file afterward.
4. bash success only proves command-level success. It does not automatically prove task completion.
5. Do not repeat the same tool call after success/noop/unchanged unless there is new evidence or a new reason.
```

### Layer C — Core Tool Contracts (always present)

#### `read_file`

```text
read_file(path, start_line?, max_lines?)
Purpose: read text from a file.
Required: path.
Optional: start_line, max_lines.
Returns: success / unchanged / error.
Guarantee: on success, the original read content is preserved in data.content.
```

#### `write_file`

```text
write_file(path, content)
Purpose: create or overwrite a text file.
Required: path, content.
Returns: success / noop / error.
Guarantee: on success or noop, the target file exactly matches the supplied content.
```

#### `bash`

```text
bash(command, timeout?, cwd?)
Purpose: execute a shell command.
Required: command.
Optional: timeout, cwd.
Returns: success / error.
Guarantee: on success, the original execution payload is preserved in data.exit_code, data.stdout, and data.stderr.
```

#### `list_dir`

```text
list_dir(path)
Purpose: list directory contents.
Required: path.
Returns: success / error.
Guarantee: on success, the original directory entries are preserved in data.entries.
```

### Layer D — Code Task Continuation Rule (always present)

```text
For code-writing tasks, after a successful write_file call, prefer bash or verify to check behavior or outputs.
Do not read the same file again unless you need specific source-level inspection that is not already available.
Do not request another write unless you can point to a specific missing requirement, failed verification result, or new evidence.
```

---

## Prompt Builder Changes

### Problem
The current prompt builder appears to collapse high-value tool outputs into short summaries.
That destroys the usefulness of structured tool contracts.

### Required fix
For tool results with high-value payloads, the prompt builder must preserve them.

### Implementation rules

#### Rule 1 — Keep raw content for `read_file`
If `read_file` succeeds:
- if the content is small enough, include full content in the next prompt
- otherwise include a structured excerpt block

#### Rule 2 — Keep raw execution payload for `bash`
If `bash` succeeds/fails:
- keep `exit_code`
- keep `stdout`
- keep `stderr`
- preserve them in structured form for the next step

#### Rule 3 — Do not reduce useful payload to line-count-only facts
Facts like “contains 57 lines” are insufficient for continuation.
They may remain as auxiliary facts, but must not replace the actual payload.

### Suggested next-prompt blocks

```text
Working file snapshots:
--- gaussian_fit.py ---
<actual file content or excerpt>
--- end ---
```

```text
Recent shell results:
- command: python gaussian_fit.py
- exit_code: 0
- stdout:
  ...
- stderr:
  ...
```

---

## Plan Progression Logic Fixes

### Problem
The current planning layer appears to over-interpret pending subgoals as a reason to keep writing.

### Required behavior change
Pending subgoals must become **checkpoints**, not immediate write instructions.

### Replace this style
```text
Suggested next unresolved subgoal (if still missing): Create histogram ...
```

### With this style
```text
Suggested next checkpoint:
The next pending subgoal is "Create histogram of generated data".
Before writing again, first decide whether the current implementation already covers this subgoal.
Prefer verify or bash over another write unless a specific missing part is identified.
```

### Required planning rule
After a successful `write_file` in a code task, the default next-step priority should be:
1. `bash` to run/verify behavior or produce outputs
2. `verify`
3. `read_file` only if specific source-level inspection is necessary
4. another `write_file` only if new evidence says the code is incomplete or incorrect

---

## Approval System Fixes

### Problem
Approval is request-scoped, causing repeated approval loops.

### Required behavior
Approval history must be stored and reused.

### Minimum requirement
For the same **turn** and the same **tool kind**, repeated write requests should not ask for approval more than once.

### Stronger recommended requirement
Allow task-scoped or file-scoped approval reuse.

### Required data model
Add approval history storage such as:

```python
class ApprovalGrant(BaseModel):
    session_id: str
    turn_id: str
    tool: str
    scope: Literal["request", "turn", "task", "file"]
    file_path: str | None = None
    granted: bool = True
```

### Required logic

#### Turn-scoped reuse
If the user approved `write_file` once in the current turn:
- additional `write_file` requests in the same turn do not ask again

#### Recommended file-scoped reuse
If the user approved `write_file` for `gaussian_fit.py` in the current task:
- later writes to `gaussian_fit.py` in the same task may reuse approval

### Hard safety rule
Approval reuse must never silently expand to unrelated tools or unrelated file targets.

---

## Additional Required Runtime Guards

### 1. No write without new evidence
If the previous successful action was `write_file(path=X)` and there is no:
- failed `bash` result,
- new user instruction,
- or specific missing requirement identified from code inspection,

then another `write_file(path=X, ...)` must be blocked with `context_required`.

Example:

```python
{
  "ok": false,
  "status": "context_required",
  "summary": "A new write requires new evidence.",
  "error": "Write blocked because there is no failed verification result, no new requirement, and no specific missing part identified."
}
```

### 2. No immediate read-after-write unless justified
If `write_file(path=X)` just returned `success` or `noop` with `exact_match=true`, then an immediate `read_file(path=X)` should require a reason.
If there is no specific reason, return `context_required`.

### 3. Keep tool guarantees narrow
Do not allow summary/facts generation code to produce claims beyond the tool guarantee boundary.

---

## Migration Steps

### Phase 1 — Strong structure foundation
1. Create `core/types.py` and `core/base.py`.
2. Replace legacy `run() -> str` pathways with `call() -> ToolObservation`.
3. Remove heuristic JSON parsing as the primary contract mechanism.
4. Make executor validate output models strictly.

### Phase 2 — Per-tool folder migration
1. Move `read_file`, `write_file`, `bash`, and `list_dir` into dedicated folders.
2. Add `schemas.py`, `spec.py`, `prompt.py`, `tool.py` for each tool.
3. Ensure registry loads tools from folder-based definitions only.

### Phase 3 — Prompt builder alignment
1. Add shared tool protocol block.
2. Add tool result trust rules block.
3. Add always-resident core tool contract block.
4. Preserve high-value payloads in prompt state.
5. Replace write-biased next-subgoal wording with checkpoint wording.

### Phase 4 — Approval memory
1. Add approval grant storage.
2. Implement turn-scoped approval reuse.
3. Optionally implement file-scoped/task-scoped reuse with conservative rules.

### Phase 5 — Runtime guards
1. Block write-without-new-evidence.
2. Block unjustified immediate read-after-write.
3. Add repeated-success tool-call prevention at runtime, not only in prompt.

---

## Acceptance Criteria

The implementation is not complete unless all of the following are true.

### Contract acceptance
- [ ] No active tool returns raw free-form text as its primary runtime contract.
- [ ] All core tools expose typed input and output models.
- [ ] Executor validates tool outputs as `ToolObservation`.

### Payload preservation
- [ ] `read_file` successful results preserve the original content in structured form.
- [ ] `bash` successful results preserve `stdout`, `stderr`, and `exit_code` in structured form.
- [ ] Prompt builder carries high-value payloads forward into the next step.

### Prompt alignment
- [ ] Shared tool protocol is always present in English.
- [ ] Tool result trust rules are always present in English.
- [ ] Core tool contracts are always present in English.
- [ ] Code-task continuation rules prefer `bash`/`verify` after write.

### Planning behavior
- [ ] Pending subgoals are presented as checkpoints, not automatic rewrite instructions.
- [ ] The agent can continue from current file state instead of blindly rewriting.

### Approval behavior
- [ ] A repeated `write_file` request within the same turn does not require repeated approval.
- [ ] Approval reuse is bounded safely by turn/file/task scope rules.

### Loop resistance
- [ ] Immediate unjustified read-after-write is blocked.
- [ ] Repeated write without new evidence is blocked.
- [ ] The agent no longer falls into `write -> read -> write -> approval` loops for the demonstrated Gaussian-fit task.

---

## Final Implementation Guidance

Focus on this priority order:

1. **Strongly typed tool contract**
2. **Preserve original tool payloads into next-step prompt state**
3. **Fix planning bias toward repeated writes**
4. **Store and reuse approval history**
5. **Add runtime guards against no-evidence rewrites**

If trade-offs are required, do **not** sacrifice strong structure or payload preservation.
Those two are the foundation of the whole fix.
