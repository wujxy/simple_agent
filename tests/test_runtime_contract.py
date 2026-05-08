from __future__ import annotations

from types import SimpleNamespace

import pytest

from simple_agent.engine.dispatcher import _handle_tool_batch
from simple_agent.engine.parser import ActionParser
from simple_agent.engine.query_loop import query_loop
from simple_agent.engine.query_state import QueryState
from simple_agent.schemas import ToolBatchAction, ToolBatchItem, ToolResult
from simple_agent.tools.core.types import ToolObservation


class FakeMemoryService:
    def __init__(self) -> None:
        self.tool_results = []
        self.step_events = []
        self.notes = []

    async def record_tool_result(self, session_id, turn_id, result, *, step=None):
        self.tool_results.append((session_id, turn_id, result, step))

    async def add_system_note(self, session_id, note, *, step=None):
        self.notes.append((session_id, note, step))

    async def record_step_event(self, session_id, payload):
        self.step_events.append((session_id, payload))


class FakeContextService:
    def __init__(self) -> None:
        self.artifacts = []
        self.step_events = []

    async def build_context(self, session, turn, state):
        return SimpleNamespace()

    async def update_artifacts_from_tool(self, session_id, tool_name, result_dict, step):
        self.artifacts.append((session_id, tool_name, result_dict, step))

    async def append_step_event(self, session_id, turn_id, step, payload):
        self.step_events.append((session_id, turn_id, step, payload))


class FakeSessionStore:
    def __init__(self) -> None:
        self.saved_turns = []
        self.saved_sessions = []

    def save_turn(self, turn):
        self.saved_turns.append(turn)

    def save_session(self, session):
        self.saved_sessions.append(session)


class FakeExecutor:
    _registry = None

    async def execute(self, session_id, turn_id, tool_name, args, **kwargs):
        if tool_name == "write_file":
            return ToolResult(
                observation=ToolObservation(ok=True, status="success", summary="should not run"),
                tool=tool_name,
                args=args,
            )

        path = args.get("path", "")
        if path == "missing.py":
            return ToolResult(
                observation=ToolObservation(
                    ok=False,
                    status="error",
                    summary="missing",
                    error="File missing.py not found",
                ),
                tool=tool_name,
                args=args,
            )

        truncated = path == "b.py"
        return ToolResult(
            observation=ToolObservation(
                ok=True,
                status="success",
                summary=f"Read {path}",
                data={
                    "path": path,
                    "content": "x",
                    "lines_read": 1,
                    "total_lines": 2 if truncated else 1,
                    "truncated": truncated,
                },
                memory={
                    "summary": f"Read {path}",
                    "references": [{"path": path, "start_line": 1, "end_line": 1}],
                },
                metadata={"path": path},
            ),
            tool=tool_name,
            args=args,
        )


def _deps(*, llm_responses=None):
    class FakeLLM:
        def __init__(self, responses):
            self.responses = list(responses or [])

        async def generate(self, prompt):
            return self.responses.pop(0)

    class FakePrompt:
        def build_action_prompt(self, state, context, tool_descriptions, include_batch=False):
            return "prompt"

    class FakeRegistry:
        def tool_descriptions_for_prompt(self):
            return ""

        def get(self, tool_name):
            return None

    class FakeLoopExecutor(FakeExecutor):
        _registry = FakeRegistry()

    class FakeVerifier:
        async def verify(self, session, state, context):
            return {"complete": True, "reason": "ok"}

    memory = FakeMemoryService()
    context = FakeContextService()
    store = FakeSessionStore()
    turn = SimpleNamespace(
        turn_id="t1",
        session_id="s1",
        user_message="read",
        max_steps=5,
        current_action=None,
        last_tool_result=None,
        verification_result=None,
        pending_action=None,
        mode="running",
        status="running",
        step_count=0,
        finished_at=None,
    )
    session = SimpleNamespace(session_id="s1", current_plan=None, active_turn_id="t1")
    deps = SimpleNamespace(
        session=session,
        turn=turn,
        session_store=store,
        session_service=SimpleNamespace(),
        memory_service=memory,
        context_service=context,
        prompt_service=FakePrompt(),
        llm_service=FakeLLM(llm_responses),
        tool_executor=FakeLoopExecutor(),
        planner=SimpleNamespace(),
        verifier=FakeVerifier(),
        parser=ActionParser(),
        tracing_service=SimpleNamespace(),
    )
    return deps, memory, context, store, turn


@pytest.mark.asyncio
async def test_dispatcher_batch_uses_action_actions_and_aggregates_results():
    deps, _memory, _context, _store, _turn = _deps()
    state = QueryState(session_id="s1", turn_id="t1", user_message="read")
    state.step_count = 2
    action = ToolBatchAction(
        type="tool_batch",
        reason="read files",
        actions=[
            ToolBatchItem(tool="read_file", args={"path": "a.py"}),
            ToolBatchItem(tool="read_file", args={"path": "b.py"}),
        ],
    )

    transition = await _handle_tool_batch(action, state, deps)

    assert transition.reason == "batch_completed:2_tools"
    assert state.last_tool_result["ok"] is True
    assert state.last_tool_result["total_tasks"] == 2
    assert state.last_tool_result["files_read"] == ["a.py", "b.py"]
    assert state.last_tool_result["truncated_files"] == ["b.py"]
    assert state.last_tool_result["references"] == [
        {"path": "a.py", "start_line": 1, "end_line": 1},
        {"path": "b.py", "start_line": 1, "end_line": 1},
    ]


@pytest.mark.asyncio
async def test_dispatcher_batch_partial_result_collects_errors():
    deps, _memory, _context, _store, _turn = _deps()
    state = QueryState(session_id="s1", turn_id="t1", user_message="read")
    state.step_count = 1
    action = ToolBatchAction(
        type="tool_batch",
        reason="read files",
        actions=[
            ToolBatchItem(tool="read_file", args={"path": "a.py"}),
            ToolBatchItem(tool="read_file", args={"path": "missing.py"}),
        ],
    )

    transition = await _handle_tool_batch(action, state, deps)

    assert transition.reason == "batch_completed:2_tools"
    assert state.last_tool_result["ok"] is False
    assert state.last_tool_result["status"] == "partial"
    assert state.last_tool_result["files_read"] == ["a.py"]
    assert state.last_tool_result["errors"] == ["File missing.py not found"]


@pytest.mark.asyncio
async def test_dispatcher_batch_rejects_non_readonly_tool():
    deps, _memory, _context, _store, _turn = _deps()
    state = QueryState(session_id="s1", turn_id="t1", user_message="write")
    action = ToolBatchAction(
        type="tool_batch",
        reason="bad",
        actions=[ToolBatchItem(tool="write_file", args={"path": "x", "content": "x"})],
    )

    transition = await _handle_tool_batch(action, state, deps)

    assert transition.reason.startswith("batch_rejected:")
    assert "write_file" in transition.reason


@pytest.mark.asyncio
async def test_query_loop_persists_batch_action_and_step_payload():
    deps, memory, _context, _store, turn = _deps(
        llm_responses=[
            '{"type": "tool_batch", "reason": "read", "actions": ['
            '{"tool": "read_file", "args": {"path": "a.py"}},'
            '{"tool": "read_file", "args": {"path": "b.py"}}'
            ']}',
            '{"type": "finish", "reason": "done", "message": "done"}',
        ]
    )
    state = QueryState(session_id="s1", turn_id="t1", user_message="read", max_steps=5)

    result = await query_loop(state, deps)

    assert result.status == "completed"
    assert turn.current_action["type"] == "finish"
    batch_step = memory.step_events[0][1]
    assert batch_step["action_type"] == "tool_batch"
    assert len(batch_step["args"]["actions"]) == 2
    assert batch_step["summary"]
