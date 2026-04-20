# CLAUDE_PLAN.md

# simple_agent v1 — Implementation Plan for Claude Code

## 1. Project goal

Build a **simple but clean AI agent framework** in Python.

This project is **not** intended to be a large production agent platform.  
It is a **v1 framework** focused on:

- understandable architecture
- structured agent loop
- clean tool abstraction
- controllable execution
- minimal but extensible memory/state design
- easy future expansion

The framework must be suitable for local development and later extension into a stronger coding/file agent.

---

## 2. Product definition

The agent should support this core workflow:

1. user gives a task
2. agent decides whether planning is needed
3. if needed, generate a structured plan
4. agent selects the next action
5. agent checks policy/permission
6. agent executes a tool if allowed
7. tool output is stored into memory
8. agent reflects and decides:
   - continue
   - retry
   - replan
   - ask user
   - finish
9. when work appears complete, agent verifies completion
10. agent outputs a final summary

The implementation must be **schema-driven**, not based on free-form tool calling text.

---

## 3. v1 design principles

Claude Code must follow these principles during implementation:

### 3.1 Keep the framework simple
Do not overbuild.
Do not add unnecessary infrastructure.

### 3.2 Strong loop, thin modules
The important part is a reliable loop:
- plan
- act
- observe
- reflect
- verify
- finish

Modules should be clean and small.

### 3.3 Structured outputs only
The LLM must output structured JSON-like action objects, not vague prose.

### 3.4 Policy before execution
Risky actions must be checked before execution.

### 3.5 Verification before finish
The agent must not directly finish without a completion check.

### 3.6 No heavy long-term memory in v1
Only short-term runtime memory is required in v1.

---

## 4. Non-goals for v1

Claude Code must **not** implement these unless they are absolutely required by the existing design:

- multi-agent collaboration
- vector database memory
- autonomous internet browsing
- plugin marketplace
- distributed workers
- GUI frontend
- async task queue
- advanced long-term memory retrieval
- multi-session persistence database
- overly complex event bus
- prompt optimization engine
- tool learning/self-modifying tools

If a feature is not needed for the core loop, skip it.

---

## 5. Required project structure

Implement the project with this folder structure:

```text
simple_agent/
├── README.md
├── pyproject.toml
├── configs/
│   ├── agent.yaml
│   ├── model.yaml
│   └── policy.yaml
├── tests/
│   ├── test_agent.py
│   ├── test_planner.py
│   ├── test_parser.py
│   ├── test_tools.py
│   ├── test_memory.py
│   └── test_policy.py
└── simple_agent/
    ├── __init__.py
    ├── agent.py
    ├── planner.py
    ├── executor.py
    ├── parser.py
    ├── policy.py
    ├── memory.py
    ├── state.py
    ├── schemas.py
    ├── llm/
    │   ├── __init__.py
    │   ├── base.py
    │   └── zhipu_client.py
    ├── prompts/
    │   ├── __init__.py
    │   ├── planner_prompt.py
    │   ├── action_prompt.py
    │   ├── verify_prompt.py
    │   └── summary_prompt.py
    ├── tools/
    │   ├── __init__.py
    │   ├── base.py
    │   ├── registry.py
    │   ├── file_tools.py
    │   └── bash_tools.py
    └── utils/
        ├── __init__.py
        ├── json_utils.py
        └── logging_utils.py
```

Important rules:

- Do **not** flatten everything into one folder.
- Do **not** create extra folders unless needed.
- Keep this structure readable and minimal.

---

## 6. File-by-file responsibilities

### 6.1 `simple_agent/agent.py`
Main orchestrator.

Responsibilities:
- accept user request
- initialize runtime state
- run planning if needed
- run execution loop
- call verifier before final finish
- return final result

Must **not** contain:
- direct tool implementations
- raw provider API code
- large prompt strings
- JSON cleanup helpers

---

### 6.2 `simple_agent/planner.py`
Planning logic.

Responsibilities:
- determine whether planning is needed
- generate structured plans
- support replan when execution hits a blocker

Planner output must be a typed schema object, not plain string text.

---

### 6.3 `simple_agent/executor.py`
Execute exactly one action.

Responsibilities:
- validate action object
- dispatch tool calls through registry
- normalize tool result
- handle execution exceptions safely

This file must not own business logic for planning.

---

### 6.4 `simple_agent/parser.py`
Parse LLM output into typed objects.

Responsibilities:
- parse LLM text into action schema
- validate required fields
- recover from malformed JSON when possible
- reject invalid outputs safely

Move `extract_json_from_text`-style logic here, not inside generic utils.

---

### 6.5 `simple_agent/policy.py`
Permission and safety checks.

Responsibilities:
- decide whether an action is allowed
- decide whether user approval is required
- block dangerous actions
- expose simple policy rules

v1 policy can be rule-based and config-driven.

---

### 6.6 `simple_agent/memory.py`
Short-term runtime memory.

Responsibilities:
- store user request
- store plan summary
- store recent actions
- store recent tool observations
- provide compact context for prompting

Do **not** inject all past tool outputs into prompts.
Only recent and relevant memory should be returned.

---

### 6.7 `simple_agent/state.py`
Runtime state object.

Responsibilities:
- track agent status
- track current plan step
- track step count
- track whether run is completed/failed/waiting approval

This is not model training state.
Do not use “epoch” terminology.

---

### 6.8 `simple_agent/schemas.py`
Central schema definitions.

Responsibilities:
- plan schema
- action schema
- tool result schema
- policy decision schema
- runtime state schema

Use one place for schemas to keep the project consistent.

---

### 6.9 `simple_agent/llm/base.py`
Abstract LLM interface.

Responsibilities:
- define provider-independent interface
- make providers swappable

---

### 6.10 `simple_agent/llm/zhipu_client.py`
Concrete ZHIPU GLM client wrapper.

Responsibilities:
- call model API
- handle retries/timeouts
- return text output
- optionally support structured output mode if available

Keep provider-specific details isolated here.

---

### 6.11 `simple_agent/prompts/*.py`
Prompt builders, split by purpose.

Files:
- `planner_prompt.py`
- `action_prompt.py`
- `verify_prompt.py`
- `summary_prompt.py`

Responsibilities:
- return prompt strings or message payloads
- isolate prompt templates by phase

Do not place all prompts into one giant file.

---

### 6.12 `simple_agent/tools/base.py`
Base tool interface.

Responsibilities:
- define base class / protocol
- define tool metadata format

---

### 6.13 `simple_agent/tools/registry.py`
Tool registry.

Responsibilities:
- register tools
- expose tool specs
- lookup tool by name
- keep agent-tool interface clean

---

### 6.14 `simple_agent/tools/file_tools.py`
Safe file tools for v1.

Implement:
- read file
- write file
- list directory
- search text in files (optional if simple enough)

Avoid implementing destructive file operations unless policy is strict.

---

### 6.15 `simple_agent/tools/bash_tools.py`
Shell execution tool.

Responsibilities:
- run shell command
- capture stdout/stderr/return code
- expose controlled interface

This tool must be policy-guarded.

---

### 6.16 `simple_agent/utils/json_utils.py`
Small JSON cleanup helpers only.

Do not turn this into a garbage dump file.

---

### 6.17 `simple_agent/utils/logging_utils.py`
Minimal logging helpers.

Keep it small.

---

## 7. Required runtime schemas

Claude Code must implement these central schemas.  
Use Pydantic if convenient; dataclasses are also acceptable if validation is sufficient.

## 7.1 PlanStep

```python
class PlanStep:
    id: str
    title: str
    description: str
    status: str  # pending | running | done | failed | skipped
    notes: str | None
```

## 7.2 TaskPlan

```python
class TaskPlan:
    goal: str
    steps: list[PlanStep]
    version: int
    summary: str | None
```

## 7.3 AgentAction

```python
class AgentAction:
    type: str  # tool_call | ask_user | replan | finish
    reason: str
    tool: str | None
    args: dict
    message: str | None
```

Rules:
- `tool` is required if `type == "tool_call"`
- `message` is required if `type == "ask_user"` or `type == "finish"`

## 7.4 ToolResult

```python
class ToolResult:
    success: bool
    tool: str
    args: dict
    output: str | None
    error: str | None
    metadata: dict
```

## 7.5 PolicyDecision

```python
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    reason: str
```

## 7.6 RunState

```python
class RunState:
    run_id: str
    user_request: str
    status: str
    step_count: int
    max_steps: int
    current_step_id: str | None
    plan: TaskPlan | None
```

---

## 8. Required agent statuses

Implement a simple status model like:

- `created`
- `planning`
- `waiting_approval`
- `running`
- `verifying`
- `completed`
- `failed`
- `aborted`

Do not add more unless clearly needed.

---

## 9. Core workflow to implement

Claude Code must implement this workflow exactly in spirit:

## 9.1 Intake
1. receive user request
2. create `RunState`
3. initialize memory
4. decide whether planning is needed

## 9.2 Planning
If planning is needed:
1. generate structured plan
2. store plan in state
3. store compact plan summary in memory

## 9.3 Execution loop
On each loop iteration:

1. build action prompt from:
   - user request
   - current plan
   - current step
   - recent memory
   - tool specs
2. ask model for exactly one next action
3. parse action into `AgentAction`
4. run policy check
5. if approval required, stop and surface approval request
6. if action is tool call, execute it
7. save tool result into memory
8. update plan step / runtime state
9. reflect whether to continue, retry, replan, ask user, or finish

## 9.4 Verification
Before final finish:
1. run verification logic
2. if verification fails, return to execution loop or mark partial failure
3. if verification succeeds, continue

## 9.5 Final response
Return:
- completion status
- what was done
- important outputs
- any failures or unresolved issues

---

## 10. Approval and policy rules for v1

Claude Code must implement a simple rule set.

Suggested defaults:

### Allowed without approval
- read file
- list directory
- inspect project structure
- generate plan
- summarize information

### Requires approval
- write file
- modify file
- run bash command

### Disallowed by default
- delete file
- destructive shell command
- network requests unless explicitly enabled

The policy system may be simple and config-backed.

Example policy config fields:

```yaml
allow_read: true
allow_list_dir: true
allow_write: false
allow_bash: false
allow_network: false
```

The exact config shape may vary, but the policy must be easy to understand.

---

## 11. Prompt design requirements

Claude Code must split prompts by phase.

## 11.1 Planning prompt
Goal:
- create a concise structured plan
- avoid overplanning for simple tasks

## 11.2 Action prompt
Goal:
- choose exactly one next action
- obey available tool list
- obey output schema strictly

## 11.3 Verification prompt
Goal:
- decide whether task is complete
- identify missing work

## 11.4 Summary prompt
Goal:
- provide concise final summary

Important:
- prompt files should expose functions/builders, not just static constants if context insertion is needed
- prompts must include schema requirements clearly

---

## 12. Tool design requirements

All tools must share a common interface.

Each tool must expose at least:
- `name`
- `description`
- `args_schema`
- `run(...)`

The registry must provide a machine-readable tool spec list for prompt injection.

### Required v1 tools

#### Read file tool
Input:
- `path`

Output:
- file content or error

#### Write file tool
Input:
- `path`
- `content`

Output:
- success/failure

#### List directory tool
Input:
- `path`

Output:
- file/directory list

#### Bash tool
Input:
- `command`

Output:
- stdout/stderr/return code

All tool outputs must be normalized into `ToolResult`.

---

## 13. Memory design requirements

v1 memory must stay simple.

Memory entries may include:
- user input
- plan summary
- action taken
- tool result summary
- important discovered facts
- user feedback

Memory API should support:
- add entry
- get recent entries
- get compact context string or structured context
- optional summarization of old entries

Important:
- do not return the entire raw history by default
- memory should be prompt-friendly

---

## 14. Parser design requirements

The parser is important.

Claude Code must implement:
- extraction of JSON block from text if model wraps it in prose
- schema validation
- graceful error when parsing fails

If the output is malformed:
- parser should either recover safely
- or raise a controlled error that the agent can handle

Do not leave parsing as ad hoc string matching in `agent.py`.

---

## 15. LLM integration requirements

Implement a provider abstraction.

### Required
- base client interface
- ZHIPU client wrapper
- API key from environment or config
- timeout/retry support
- clean error surface

### Optional
- structured output mode if supported by provider
- temperature/model config from yaml

Do not hardcode configuration values inside business logic.

---

## 16. Configuration requirements

Use config files under `configs/`.

### `configs/model.yaml`
Possible fields:
- provider
- model_name
- temperature
- max_tokens
- timeout

### `configs/policy.yaml`
Possible fields:
- allow_read
- allow_write
- allow_bash
- require_approval_for_write
- require_approval_for_bash

### `configs/agent.yaml`
Possible fields:
- max_steps
- enable_planning
- planning_threshold
- memory_window

These files should stay simple and readable.

---

## 17. Testing requirements

Claude Code must write tests.

Minimum required tests:

### `test_parser.py`
- valid JSON parses correctly
- malformed JSON fails safely
- missing required fields are detected

### `test_tools.py`
- read file tool works
- write file tool works on temp file
- bash tool returns structured result

### `test_memory.py`
- add entries works
- recent retrieval works
- compact context works

### `test_policy.py`
- allowed action passes
- write action can require approval
- blocked action is denied

### `test_planner.py`
- planner returns structured plan object

### `test_agent.py`
- basic task loop runs end-to-end with mocked LLM

Tests may use mocked model outputs to avoid real API calls.

---

## 18. README requirements

Claude Code must also update or create `README.md`.

README should include:
- project goal
- folder structure
- install steps
- config setup
- how to run demo
- how approval/policy works
- how to run tests

Keep README simple and practical.

---

## 19. Coding style requirements

Claude Code must follow these coding rules:

- use Python typing
- prefer small functions
- avoid giant classes
- keep module boundaries clean
- do not duplicate schemas in multiple files
- do not place parsing logic in agent loop
- do not place prompt strings inline in `agent.py`
- avoid magical globals
- prefer explicit names over abbreviations

Error handling must be explicit and readable.

---

## 20. v1 implementation phases

Claude Code should implement in this order.

## Phase 1 — Project skeleton
Create:
- folder structure
- base files
- schema file
- config files
- README stub

## Phase 2 — Tool system
Implement:
- base tool
- registry
- read/write/list/bash tools
- normalized tool result

## Phase 3 — Core runtime
Implement:
- state
- memory
- parser
- policy
- executor

## Phase 4 — LLM and prompts
Implement:
- base LLM client
- ZHIPU client
- planner/action/verify/summary prompt builders

## Phase 5 — Agent loop
Implement:
- planning decision
- action loop
- verification
- finish flow

## Phase 6 — Tests and cleanup
Implement:
- required tests
- README completion
- minor refactor for clarity

Claude Code must not jump straight into polishing before the loop works.

---

## 21. Acceptance criteria

The project is complete only if all of the following are true:

### Architecture
- folder structure matches the plan closely
- responsibilities are separated cleanly

### Functionality
- agent can accept a task
- agent can produce a plan when needed
- agent can select a tool action
- agent can execute tools through registry
- agent can store observations in memory
- agent can apply policy checks
- agent can verify completion before finish

### Quality
- parser is isolated
- prompts are isolated
- provider code is isolated
- tests exist and pass

### Simplicity
- no major overengineering
- no unrelated features added

---

## 22. Explicit anti-overengineering instructions

Claude Code must **not** do the following unless absolutely necessary:

- do not add database layer
- do not add web server
- do not add async message queue
- do not add event sourcing
- do not add plugin discovery system
- do not add vector memory
- do not add agent graph engine
- do not add too many abstractions for a v1 project

The goal is a clean, teachable, extensible **simple agent framework**, not an enterprise platform.

---

## 23. Suggested minimal public API

A simple entrypoint is enough.

Example target usage:

```python
from simple_agent.agent import SimpleAgent

agent = SimpleAgent.from_config("configs")
result = agent.run("Read README.md and summarize project structure")
print(result)
```

If a different API shape is more natural, it is acceptable, but it must remain simple.

---

## 24. Deliverables

Claude Code should finish with these deliverables:

1. implemented project structure
2. working core agent loop
3. working tool system
4. ZHIPU model integration
5. config files
6. tests
7. README

---

## 25. Final instruction to Claude Code

Implement this project exactly as a **clean v1 simple agent framework**.

Prioritize:
- clarity
- correctness
- separation of responsibility
- minimalism
- extensibility

Do not overbuild.
Do not invent extra subsystems.
Do not ignore tests.
Do not collapse all logic back into `agent.py`.

The end result must be something a developer can read and understand quickly, while still being strong enough to serve as a real base for future agent development.
