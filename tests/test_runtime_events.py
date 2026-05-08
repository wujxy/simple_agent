from __future__ import annotations

from types import SimpleNamespace

import pytest

from simple_agent.engine.parser import ActionParser
from simple_agent.engine.query_loop import query_loop
from simple_agent.engine.query_state import QueryState
from simple_agent.runtime.cli_renderer import CliEventRenderer
from simple_agent.runtime.event_bus import EventBus
from simple_agent.runtime.event_types import (
    Event,
    RUNTIME_ACTION_PARSED,
    RUNTIME_CONTEXT_BUDGET_UPDATED,
    RUNTIME_LLM_COMPLETED,
    RUNTIME_STEP_COMPLETED,
    RUNTIME_STEP_STARTED,
    RUNTIME_TOOL_COMPLETED,
    RUNTIME_TOOL_STARTED,
)
from simple_agent.schemas import ToolResult
from simple_agent.tools.core.types import ToolObservation


@pytest.mark.asyncio
async def test_event_bus_wildcard_subscriber_receives_all_events():
    bus = EventBus()
    seen = []
    bus.subscribe("*", lambda event: seen.append(event.type))

    await bus.publish(Event(
        event_id="evt_1",
        session_id="s1",
        turn_id="t1",
        type="custom.event",
        source="test",
    ))

    assert seen == ["custom.event"]


def test_cli_renderer_formats_action_budget_and_tool_result():
    renderer = CliEventRenderer()

    action_text = renderer.render(Event(
        event_id="evt_1",
        session_id="s1",
        turn_id="t1",
        type=RUNTIME_ACTION_PARSED,
        source="test",
        payload={
            "step": 3,
            "max_steps": 20,
            "action_type": "tool_call",
            "tool_name": "read_file",
            "target": "app.py",
            "reason": "inspect the file before editing",
        },
    ))
    assert "[step 3/20][normal] tool_call: read_file -> app.py" in action_text
    assert "intent: inspect the file before editing" in action_text

    budget_text = renderer.render(Event(
        event_id="evt_2",
        session_id="s1",
        turn_id="t1",
        type=RUNTIME_CONTEXT_BUDGET_UPDATED,
        source="test",
        payload={
            "prompt": {"total_chars": 12000, "estimated_tokens": 3000, "token_budget": 32000, "token_percent": 9},
            "memory": {"current_chars": 8000, "char_budget": 12000, "threshold_percent": 80, "remaining_chars": 1600},
            "working_set": {"files_tracked": 5, "files_projected": 4, "modified_paths": 1, "grep_hits": 2},
            "artifact": {"projected_snapshots": 2},
        },
    ))
    assert "context: 12000 chars" in budget_text
    assert "memory: 8000 / 12000 chars" in budget_text
    assert "working set: 5 files tracked" in budget_text

    tool_text = renderer.render(Event(
        event_id="evt_3",
        session_id="s1",
        turn_id="t1",
        type=RUNTIME_TOOL_COMPLETED,
        source="test",
        payload={
            "tool_name": "read_file",
            "ok": True,
            "status": "success",
            "summary": "Read app.py",
            "facts": ["app.py has 10 lines"],
        },
    ))
    assert "tool: read_file completed ok" in tool_text
    assert "summary: Read app.py" in tool_text


class FakeMemoryService:
    async def record_tool_result(self, *args, **kwargs):
        pass

    async def add_system_note(self, *args, **kwargs):
        pass

    async def record_step_event(self, *args, **kwargs):
        pass

    def budget_snapshot(self, session_id):
        return {
            "current_chars": 100,
            "char_budget": 12000,
            "threshold_percent": 80,
            "remaining_chars": 9500,
        }


class FakeContextService:
    async def build_context(self, session, turn, state):
        return SimpleNamespace(working_set_block="", artifact_snapshot="", prompt_memory_block="")

    async def update_artifacts_from_tool(self, *args, **kwargs):
        pass

    async def append_step_event(self, *args, **kwargs):
        pass

    def runtime_snapshot(self, session_id, context):
        return {
            "working_set": {"files_tracked": 0, "files_projected": 0, "modified_paths": 0, "grep_hits": 0},
            "artifact": {"projected_snapshots": 0},
        }


class FakeSessionStore:
    def save_turn(self, turn):
        pass

    def save_session(self, session):
        pass


class FakePromptService:
    def __init__(self):
        self._stats = {}

    def build_action_prompt(self, state, context, tool_descriptions, include_batch=False):
        prompt = "prompt"
        self._stats = {"total_chars": len(prompt), "layers": {"context": 0}}
        return prompt

    def last_action_prompt_stats(self):
        return self._stats


class FakeLLM:
    _config = {"context_budget_tokens": 32000}

    def __init__(self):
        self.responses = [
            '{"type": "tool_call", "reason": "read the file", "tool": "read_file", "args": {"path": "app.py"}}',
            '{"type": "finish", "reason": "done", "message": "done"}',
        ]

    async def generate(self, prompt):
        return self.responses.pop(0)


class FakeExecutor:
    class Registry:
        def tool_descriptions_for_prompt(self):
            return ""

    _registry = Registry()

    async def execute(self, session_id, turn_id, tool_name, args, **kwargs):
        return ToolResult(
            observation=ToolObservation(
                ok=True,
                status="success",
                summary="Read app.py",
                data={"path": "app.py", "content": "x", "total_lines": 1, "lines_read": 1, "truncated": False},
            ),
            tool=tool_name,
            args=args,
        )


@pytest.mark.asyncio
async def test_query_loop_emits_runtime_events_for_tool_call_turn():
    bus = EventBus()
    events = []
    bus.subscribe("*", lambda event: events.append(event.type))
    turn = SimpleNamespace(
        turn_id="t1",
        session_id="s1",
        step_count=0,
        max_steps=5,
        mode="running",
        status="running",
        current_action=None,
        last_tool_result=None,
        verification_result=None,
        pending_action=None,
        finished_at=None,
    )
    deps = SimpleNamespace(
        session=SimpleNamespace(session_id="s1", current_plan=None, active_turn_id="t1"),
        turn=turn,
        session_store=FakeSessionStore(),
        session_service=SimpleNamespace(),
        memory_service=FakeMemoryService(),
        context_service=FakeContextService(),
        prompt_service=FakePromptService(),
        llm_service=FakeLLM(),
        tool_executor=FakeExecutor(),
        planner=SimpleNamespace(),
        verifier=SimpleNamespace(verify=lambda *args, **kwargs: {"complete": True}),
        parser=ActionParser(),
        tracing_service=SimpleNamespace(),
        event_bus=bus,
    )

    class FakeVerifier:
        async def verify(self, *args, **kwargs):
            return {"complete": True}

    deps.verifier = FakeVerifier()
    state = QueryState(session_id="s1", turn_id="t1", user_message="read app.py", max_steps=5)

    result = await query_loop(state, deps)

    assert result.status == "completed"
    assert RUNTIME_STEP_STARTED in events
    assert RUNTIME_CONTEXT_BUDGET_UPDATED in events
    assert RUNTIME_LLM_COMPLETED in events
    assert RUNTIME_ACTION_PARSED in events
    assert RUNTIME_TOOL_STARTED in events
    assert RUNTIME_TOOL_COMPLETED in events
    assert RUNTIME_STEP_COMPLETED in events
