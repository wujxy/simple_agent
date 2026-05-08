from __future__ import annotations

from types import SimpleNamespace

import pytest

from simple_agent.engine.parser import ActionParser
from simple_agent.engine.query_loop import query_loop
from simple_agent.engine.query_state import QueryState
from simple_agent.hooks.pre_tool_use import ToolInvocation
from simple_agent.policy.policy_engine import PolicyEngine
from simple_agent.runtime.event_bus import EventBus
from simple_agent.runtime.event_types import RUNTIME_ACTION_PARSED, RUNTIME_STEP_STARTED
from simple_agent.runtime.modes import ModeService, RunMode


def test_mode_service_default_policies():
    service = ModeService({"runtime": {"max_steps": 12, "max_tool_calls": 7, "max_writes": 3}})

    normal = service.policy_for_mode(RunMode.NORMAL)
    plan = service.policy_for_mode(RunMode.PLAN)
    yolo = service.policy_for_mode(RunMode.YOLO)

    assert normal.allow_read is True
    assert normal.allow_write is False
    assert normal.require_approval_for_write is True
    assert plan.planning_required is True
    assert plan.strict_verify is True
    assert yolo.allow_write is True
    assert yolo.allow_bash is True
    assert yolo.max_tool_calls == 7
    assert service.normalize_mode("bad").value == "normal"


@pytest.mark.asyncio
async def test_policy_engine_uses_normal_plan_yolo_boundaries():
    service = ModeService({"runtime": {"max_tool_calls": 2, "max_writes": 1}})
    engine = PolicyEngine({}, mode_service=service)

    service.start_turn("s1", "normal_t", "normal")
    read = await engine.evaluate(ToolInvocation("s1", "normal_t", "read_file", {"path": "a.py"}))
    write = await engine.evaluate(ToolInvocation("s1", "normal_t", "edit_file", {"path": "a.py"}))
    bash = await engine.evaluate(ToolInvocation("s1", "normal_t", "bash", {"command": "echo ok"}))

    assert read.status == "allow"
    assert write.status == "ask"
    assert bash.status == "ask"

    service.start_turn("s1", "plan_t", "plan")
    plan_write = await engine.evaluate(ToolInvocation("s1", "plan_t", "write_file", {"path": "a.py"}))
    assert plan_write.status == "ask"

    service.start_turn("s1", "yolo_t", "yolo")
    yolo_write = await engine.evaluate(ToolInvocation("s1", "yolo_t", "write_file", {"path": "a.py"}))
    yolo_bash = await engine.evaluate(ToolInvocation("s1", "yolo_t", "bash", {"command": "echo ok"}))
    blocked = await engine.evaluate(ToolInvocation("s1", "yolo_t", "bash", {"command": "rm -rf /tmp/x"}))

    assert yolo_write.status == "allow"
    assert yolo_bash.status == "allow"
    assert blocked.status == "deny"


def test_mode_service_denies_hard_limit_excesses():
    service = ModeService({"runtime": {"max_tool_calls": 1, "max_writes": 1}})
    service.start_turn("s1", "t1", "yolo")

    assert service.evaluate_tool_boundary("s1", "t1", "read_file", {"path": "a.py"}).status == "allow"
    service.record_tool_started("s1", "t1", "read_file")
    assert service.evaluate_tool_boundary("s1", "t1", "read_file", {"path": "b.py"}).status == "deny"

    service.start_turn("s1", "t2", "yolo")
    assert service.evaluate_tool_boundary("s1", "t2", "write_file", {"path": "a.py"}).status == "allow"
    service.record_tool_started("s1", "t2", "write_file")
    assert service.evaluate_tool_boundary("s1", "t2", "edit_file", {"path": "b.py"}).status == "deny"


class FakeMemoryService:
    def __init__(self):
        self.notes = []
        self.step_events = []

    async def record_tool_result(self, *args, **kwargs):
        pass

    async def add_system_note(self, session_id, note, *args, **kwargs):
        self.notes.append(note)

    async def record_step_event(self, session_id, payload):
        self.step_events.append(payload)

    def budget_snapshot(self, session_id):
        return {}


class FakeContextService:
    async def build_context(self, session, turn, state):
        return SimpleNamespace(working_set_block="", artifact_snapshot="", prompt_memory_block="")

    async def update_artifacts_from_tool(self, *args, **kwargs):
        pass

    async def append_step_event(self, *args, **kwargs):
        pass

    def runtime_snapshot(self, session_id, context):
        return {}


class FakeStore:
    def save_turn(self, turn):
        pass

    def save_session(self, session):
        pass


class FakePrompt:
    def __init__(self):
        self._stats = {}

    def build_action_prompt(self, state, context, tool_descriptions, include_batch=False):
        self._stats = {"total_chars": 6, "layers": {}}
        return "prompt"

    def last_action_prompt_stats(self):
        return self._stats


class FakeLLM:
    _config = {"context_budget_tokens": 32000}

    async def generate(self, prompt):
        return '{"type": "finish", "reason": "done", "message": "done"}'


class FakeExecutor:
    class Registry:
        def tool_descriptions_for_prompt(self):
            return ""

    _registry = Registry()


class FakePlanner:
    def needs_planning(self, user_message):
        return True

    async def generate_plan(self, user_message):
        return SimpleNamespace(
            overview="Inspect and verify the requested change",
            model_dump=lambda: {
                "overview": "Inspect and verify the requested change",
                "steps": [{"step_id": "1", "title": "Inspect", "status": "pending"}],
            },
        )


class FakeVerifier:
    async def verify(self, *args, **kwargs):
        return {"complete": True}


@pytest.mark.asyncio
async def test_plan_mode_forces_complex_task_plan_before_llm_action():
    bus = EventBus()
    action_payloads = []
    step_payloads = []
    bus.subscribe(RUNTIME_ACTION_PARSED, lambda event: action_payloads.append(event.payload))
    bus.subscribe(RUNTIME_STEP_STARTED, lambda event: step_payloads.append(event.payload))

    mode_service = ModeService({"runtime": {"max_steps": 5}})
    mode_service.start_turn("s1", "t1", "plan")
    turn = SimpleNamespace(
        turn_id="t1",
        session_id="s1",
        user_message="modify several files and verify",
        step_count=0,
        max_steps=5,
        mode="running",
        status="running",
        run_mode="plan",
        current_action=None,
        last_tool_result=None,
        verification_result=None,
        pending_action=None,
        finished_at=None,
    )
    session = SimpleNamespace(session_id="s1", current_plan=None, active_turn_id="t1", run_mode="plan")
    deps = SimpleNamespace(
        session=session,
        turn=turn,
        session_store=FakeStore(),
        session_service=SimpleNamespace(),
        memory_service=FakeMemoryService(),
        context_service=FakeContextService(),
        prompt_service=FakePrompt(),
        llm_service=FakeLLM(),
        tool_executor=FakeExecutor(),
        planner=FakePlanner(),
        verifier=FakeVerifier(),
        parser=ActionParser(),
        tracing_service=SimpleNamespace(),
        event_bus=bus,
        mode_service=mode_service,
    )
    state = QueryState(
        session_id="s1",
        turn_id="t1",
        user_message="modify several files and verify",
        max_steps=5,
        run_mode="plan",
    )

    result = await query_loop(state, deps)

    assert result.status == "completed"
    assert action_payloads[0]["action_type"] == "plan"
    assert action_payloads[0]["run_mode"] == "plan"
    assert step_payloads[0]["run_mode"] == "plan"
    assert session.current_plan is not None
