# Context + Memory Phase 1 Reconstruction Implementation Plan

> Owner: Codex
>
> Spec source: `docs/claude/CONTEXT_MEMORY_RECONSTRUCT.md`
>
> Scope: Phase 1 only. This plan supersedes the earlier GLM draft.

## Goal

Separate Context, Memory, and Compact responsibilities enough to establish the new runtime path:

```text
query_loop
  -> record raw / structured events
  -> memory_service.build_prompt_memory(...)
  -> context_service.build_context(...)
  -> prompt_service.build_action_prompt(...)
  -> llm.generate(...)
```

Phase 1 must produce a working compact lifecycle:

```text
hot memory -> compacted memory -> evicted compacted memory
```

The goal is not perfect summarization. The goal is to put the ownership boundaries in the right place and make prompt memory budget-managed.

## Architectural Decisions

1. `ContextService` is the truth/context side. In Phase 1 it may still build objective, execution-state, artifact snapshot, and next-decision blocks, but it must stop owning prompt memory strategy.
2. `MemoryService` is the prompt memory manager. It defines memory items, controls budget, triggers compact, writes compact results back, and renders the unified prompt memory block.
3. `CompactService` is called by `MemoryService`. Its public API is async from the start so Phase 3 can replace the rule-based stub with LLM compact without breaking callers.
4. `PromptService` only assembles prompt text. It should not decide what memory is important.
5. Legacy prompt fields may remain on `PromptContext` for compatibility, but Phase 1 must not keep adding new dependencies to legacy memory blocks.

## Phase 1 Boundary

In scope:

- Add `MemoryStore.replace_all()` and `MemoryStore.count()`.
- Add async `CompactService.maybe_compact()`.
- Upgrade `MemoryService` into a budget-aware prompt memory manager.
- Add `PromptContext.prompt_memory_block`.
- Make `ContextService.build_context()` call `MemoryService.build_prompt_memory()`.
- Inject `prompt_memory_block` into `action_prompt.py`.
- Record step-level memory in `query_loop.py` after dispatch.
- Wire `CompactService` in `SessionRuntime`.
- Add focused unit and integration tests.

Out of scope:

- LLM-generated compact summaries.
- Tokenizer-level budget calculation.
- Full `ContextLedger` implementation.
- UI/debug history pagination.
- Removing every legacy field from dataclasses.
- Sub-agent context isolation.

## Important Corrections From The Earlier Draft

- `CompactService.maybe_compact()` is async, not sync.
- `ContextService` should not continue building prompt memory through `_build_confirmed_facts()`, `_build_recent_observations()`, `_build_working_set()`, or `SessionSummaryService.get_compact_summary()`.
- `record_step_event()` must capture useful execution facts, not only `transition.reason`.
- Prompt ordering should follow the reconstruct spec: objective, execution state, prompt memory, artifact snapshot, next decision.
- Commits are optional. Do not auto-commit unless the user asks.

## Target File Changes

| File | Action | Responsibility |
|---|---|---|
| `simple_agent/memory/memory_store.py` | Modify | Add compact writeback helpers |
| `simple_agent/memory/compact_service.py` | Create | Async v0 rule-based compact and eviction |
| `simple_agent/memory/memory_service.py` | Modify | Structured memory item writer, compact trigger, prompt renderer |
| `simple_agent/context/context_layers.py` | Modify | Add `prompt_memory_block` to `PromptContext` |
| `simple_agent/context/context_service.py` | Modify | Delegate prompt memory to `MemoryService` |
| `simple_agent/prompts/action_prompt.py` | Modify | Render unified memory block in prompt |
| `simple_agent/engine/query_loop.py` | Modify | Record step event after dispatch |
| `simple_agent/runtime/session_runtime.py` | Modify | Wire `CompactService` |
| `tests/test_compact_service.py` | Create | Compact lifecycle tests |
| `tests/test_memory_v2.py` | Create | Store and MemoryService tests |
| `tests/test_context_memory_integration.py` | Create | Prompt-memory integration smoke tests |

## Memory Item Schema

Use a plain dict in Phase 1. Keep the schema stable enough for compact and future debugging.

```python
{
    "id": "mem_step_12",
    "kind": "user|tool|system|step|summary|verify|plan",
    "state": "hot|compacted",
    "priority": "high|normal|low",
    "created_at_step": 12,
    "source_range": {"from_step": 3, "to_step": 8},
    "content": "...",
    "summary": "...",
    "facts": [],
    "changed_paths": [],
    "errors": [],
    "decisions": [],
    "verification": [],
}
```

Minimum Phase 1 requirements:

- Every new item gets `id`, `kind`, `state`, `priority`, `created_at_step`, and either `content` or `summary`.
- Step/tool items should carry `facts`, `changed_paths`, and `errors` when known.
- Compacted summary items must carry `source_range`.

## Task 1: MemoryStore Writeback Helpers

Files:

- Modify: `simple_agent/memory/memory_store.py`
- Test: `tests/test_memory_v2.py`

Implementation:

```python
def replace_all(self, session_id: str, items: list[dict]) -> None:
    self._data[session_id] = list(items)

def count(self, session_id: str) -> int:
    return len(self._data.get(session_id, []))
```

Tests:

- `replace_all()` replaces existing session memory.
- `replace_all()` works for an empty session.
- `count()` returns `0` for missing sessions and current item count for populated sessions.

Verification:

```bash
python -m pytest tests/test_memory_v2.py::TestMemoryStoreV2 -v
```

## Task 2: Async CompactService v0

Files:

- Create: `simple_agent/memory/compact_service.py`
- Test: `tests/test_compact_service.py`

Public API:

```python
class CompactService:
    def __init__(
        self,
        char_budget: int = 12000,
        trigger_ratio: float = 0.8,
        hot_keep_last: int = 8,
        min_candidates: int = 6,
    ) -> None: ...

    async def maybe_compact(self, items: list[dict], *, current_step: int) -> dict: ...
```

Behavior:

- Estimate prompt memory size by chars from `content`, `summary`, `facts`, `errors`, `decisions`, and `verification`.
- If size is below `char_budget * trigger_ratio`, return unchanged items.
- Keep the latest `hot_keep_last` hot items uncompressed.
- Compact older hot items into one `kind="summary", state="compacted"` item.
- Preserve existing compacted items unless eviction is required.
- If still over `char_budget`, evict oldest compacted items only.
- Never evict hot items in v0.
- Provide `_generate_summary_via_llm()` as an async placeholder for Phase 3.

Summary item shape:

```python
{
    "id": f"mem_summary_{current_step}",
    "kind": "summary",
    "state": "compacted",
    "priority": "normal",
    "created_at_step": current_step,
    "source_range": {"from_step": first_step, "to_step": last_step},
    "content": rendered_summary,
    "summary": rendered_summary,
}
```

Tests:

- No compact under threshold.
- No compact when candidate count is below `min_candidates`.
- Old hot items are replaced by one compacted summary.
- Summary includes `source_range`.
- Existing compacted summaries can be evicted when still over budget.
- Hot items are never evicted.
- `maybe_compact()` is awaited in tests.

Verification:

```bash
python -m pytest tests/test_compact_service.py -v
```

## Task 3: PromptContext Field

Files:

- Modify: `simple_agent/context/context_layers.py`

Add `prompt_memory_block: str = ""` to `PromptContext`, and include it in `to_dict()`.

Keep legacy fields for compatibility:

- `confirmed_facts`
- `compact_memory_summary`
- `working_set_summary`
- `recent_observations`

Do not remove these in Phase 1 unless all tests and callers are adjusted.

Verification:

```bash
python -m pytest tests/ -v --ignore=tests/test_memory.py
```

## Task 4: MemoryService as Prompt Memory Manager

Files:

- Modify: `simple_agent/memory/memory_service.py`
- Test: `tests/test_memory_v2.py`

Constructor:

```python
def __init__(
    self,
    store: MemoryStore,
    *,
    compact_service: CompactService | None = None,
) -> None:
    self._store = store
    self._compact = compact_service
    self._next_id = 0
```

Required methods:

```python
async def record_user_message(self, session_id: str, text: str, *, step: int | None = None) -> None: ...
async def record_tool_result(self, session_id: str, turn_id: str, result: dict, *, step: int | None = None) -> None: ...
async def add_system_note(self, session_id: str, note: str, *, step: int | None = None) -> None: ...
async def record_step_event(self, session_id: str, payload: dict) -> None: ...
async def record_verify_result(self, session_id: str, payload: dict) -> None: ...
async def build_prompt_memory(self, session_id: str, *, current_step: int) -> str: ...
async def get_recent(self, session_id: str, limit: int = 10) -> list[dict]: ...
```

Implementation requirements:

- Existing callers of `record_user_message()`, `record_tool_result()`, `add_system_note()`, and `get_recent()` must keep working.
- Existing role fields may stay for compatibility, but new items must also include `kind` and `state`.
- `build_prompt_memory()` must `await self._compact.maybe_compact(...)` when compact service exists.
- On compact, call `MemoryStore.replace_all()` with `result["new_items"]`.
- Rendering should include compacted summaries, recent steps, facts, modified paths, errors, and verification notes.

`record_step_event()` should accept and store:

```python
{
    "step": 1,
    "action_type": "tool_call",
    "tool_name": "read_file",
    "args": {"path": "x.py"},
    "ok": True,
    "summary": "Read x.py",
    "facts": ["..."],
    "changed_paths": ["..."],
    "errors": ["..."],
    "verification": ["..."],
}
```

`SessionSummaryService`:

- Remove it from new runtime wiring.
- It may remain as a deprecated compatibility wrapper during Phase 1 only if existing imports require it.
- It must not be used by `ContextService.build_context()` anymore.

Tests:

- User, system, tool, step, and verify records create structured hot memory items.
- Items include `id`, `kind`, `state`, `created_at_step`, and `priority`.
- `build_prompt_memory()` renders useful step/tool facts.
- `build_prompt_memory()` triggers compact and writes compacted items back.
- Legacy `get_recent()` still returns recent store items.

Verification:

```bash
python -m pytest tests/test_memory_v2.py -v
```

## Task 5: ContextService Delegates Prompt Memory

Files:

- Modify: `simple_agent/context/context_service.py`

Required changes:

- Remove `SessionSummaryService` usage from `ContextService`.
- `build_context()` must call:

```python
prompt_memory_block = await self._memory.build_prompt_memory(
    session.session_id,
    current_step=state.step_count,
)
```

- Return `PromptContext(prompt_memory_block=prompt_memory_block, ...)`.
- Keep objective, execution state, artifact snapshot, and next decision point.
- Do not call `_build_confirmed_facts()`, `_build_recent_observations()`, `_build_working_set()`, or `get_compact_summary()` from `build_context()`.

Phase 1 compatibility:

- The helper methods may remain in the file temporarily if deletion would churn tests.
- The legacy fields may be returned empty.
- `artifact_state` and `update_artifacts_from_tool()` stay in `ContextService`.

Target shape:

```python
return PromptContext(
    objective_block=objective,
    execution_state=execution_state,
    artifact_snapshot=artifact_snapshot,
    next_decision_point=next_decision,
    prompt_memory_block=prompt_memory_block,
)
```

Verification:

```bash
python -m pytest tests/ -v --ignore=tests/test_memory.py
```

## Task 6: Prompt Injection

Files:

- Modify: `simple_agent/prompts/action_prompt.py`

`build_context_prompt()` should render blocks in this order:

1. Objective
2. Execution state
3. Memory
4. Artifact snapshot
5. Next decision point

Implementation shape:

```python
if prompt_context.objective_block:
    blocks.append(prompt_context.objective_block)

if prompt_context.execution_state:
    blocks.append(f"Execution state:\n{prompt_context.execution_state}")

if prompt_context.prompt_memory_block:
    blocks.append(f"Memory:\n{prompt_context.prompt_memory_block}")

if prompt_context.artifact_snapshot:
    blocks.append(prompt_context.artifact_snapshot)

if prompt_context.next_decision_point:
    blocks.append(prompt_context.next_decision_point)
```

Do not render `compact_memory_summary`.

Legacy compatibility:

- If tests or runtime still need `confirmed_facts`, `working_set_summary`, or `recent_observations`, they may be rendered after the primary blocks.
- Prefer leaving them empty from `ContextService` so the new memory block is the effective source.

Verification:

```bash
python -m pytest tests/ -v --ignore=tests/test_memory.py
```

## Task 7: query_loop Step Event Recording

Files:

- Modify: `simple_agent/engine/query_loop.py`

Record a memory step event after `dispatch_action()` and before `apply_transition()` or immediately after it, as long as the stored payload reflects the action and transition result.

Minimum payload:

```python
payload = {
    "step": state.step_count,
    "action_type": action.type,
    "tool_name": action.tool or "",
    "args": action.args or {},
    "ok": transition.type not in ("failed",),
    "summary": transition.message or transition.reason or "",
}
```

Enrich payload when available:

- From `state.last_tool_result` or transition payload: `facts`, `changed_paths`, `errors`.
- From verification result: `verification`.
- For failed actions: include the failure reason in `errors`.

Recommended helper shape inside `query_loop.py`:

```python
def _build_step_memory_payload(action, state, transition) -> dict:
    ...
```

This keeps the loop readable and gives tests a stable target.

Verification:

```bash
python -m pytest tests/ -v --ignore=tests/test_memory.py
```

## Task 8: Runtime Wiring

Files:

- Modify: `simple_agent/runtime/session_runtime.py`

Required changes:

```python
from simple_agent.memory.compact_service import CompactService
from simple_agent.memory.memory_service import MemoryService

memory_store = MemoryStore()
compact_service = CompactService()
memory_service = MemoryService(memory_store, compact_service=compact_service)

self._registry.register("memory_store", memory_store)
self._registry.register("compact_service", compact_service)
self._registry.register("memory_service", memory_service)
```

Do not register `SessionSummaryService` as a runtime dependency in the new path.

Verification:

```bash
python -m pytest tests/ -v --ignore=tests/test_memory.py
```

## Task 9: Integration Smoke Tests

Files:

- Create: `tests/test_context_memory_integration.py`

Required tests:

1. Recording a user message and step event, then calling `ContextService.build_context()`, produces a non-empty `prompt_memory_block`.
2. `action_prompt.build_context_prompt()` includes `Memory:` before artifact snapshot.
3. Low char budget triggers compact through `MemoryService.build_prompt_memory()`.
4. The store contains at least one `state="compacted"` item after compact.

Verification:

```bash
python -m pytest tests/test_context_memory_integration.py -v
```

## Full Verification

Run the focused tests first:

```bash
python -m pytest tests/test_compact_service.py tests/test_memory_v2.py tests/test_context_memory_integration.py -v
```

Then run the broader suite:

```bash
python -m pytest tests/ -v --ignore=tests/test_memory.py
```

If `tests/test_memory.py` is still tied to the old memory implementation, leave it ignored in Phase 1 and document that it needs replacement or migration in Phase 2.

## Acceptance Criteria

Phase 1 is complete when:

- Prompt context contains a unified `prompt_memory_block`.
- `action_prompt.py` renders that block as the primary memory section.
- `ContextService.build_context()` no longer builds memory summaries from `SessionSummaryService` or memory-specific legacy helpers.
- `MemoryService.build_prompt_memory()` triggers async compact and writes back compacted memory.
- Compact keeps recent hot items, replaces older hot items, and evicts only compacted items.
- Step memory contains enough local execution history to help the next loop iteration.
- Runtime wires `CompactService`.
- Focused and integration tests pass.

## Phase 2 Follow-ups

These are intentionally not part of Phase 1:

- Move `working_set` fully into hot memory items.
- Move confirmed facts and recent observations fully into `MemoryService` render output.
- Delete `SessionSummaryService`.
- Delete `compact_memory_summary` prompt path and eventually remove the dataclass field.
- Add explicit `ContextLedger` models and append/get APIs.
- Record raw message, step, plan, artifact, and permission events in `ContextService`.

## Implementation Notes For The Next Worker

- Make the smallest code changes that establish the new path.
- Do not auto-commit unless explicitly asked.
- Preserve existing public method signatures where current callers depend on them.
- Prefer adding compatibility parameters such as `step: int | None = None` over breaking existing calls.
- Keep compact deterministic in v0 so tests are stable.
- Avoid using tokenizer dependencies in Phase 1.
