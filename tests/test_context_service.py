import pytest

from simple_agent.context.context_service import ContextService
from simple_agent.memory.memory_service import MemoryService
from simple_agent.memory.memory_store import MemoryStore


def _make_context() -> ContextService:
    return ContextService(MemoryService(MemoryStore()))


class TestContextServiceLedger:
    @pytest.mark.asyncio
    async def test_append_message_event(self):
        context = _make_context()
        await context.append_message_event("s1", "user", "hello", "t1")
        segment = await context.get_raw_segment("s1", 1, 3)
        assert segment[0]["kind"] == "message"
        assert segment[0]["role"] == "user"
        assert segment[0]["content"] == "hello"
        assert segment[0]["turn_id"] == "t1"

    @pytest.mark.asyncio
    async def test_append_step_event_and_recent_steps(self):
        context = _make_context()
        for step in range(3):
            await context.append_step_event("s1", "t1", step + 1, {"summary": f"step {step + 1}"})
        recent = await context.get_recent_steps("s1", limit=2)
        assert [item["step_id"] for item in recent] == [2, 3]
        assert recent[-1]["payload"]["summary"] == "step 3"

    @pytest.mark.asyncio
    async def test_update_artifacts_from_tool_appends_artifact_event(self):
        context = _make_context()
        await context.update_artifacts_from_tool("s1", "read_file", {
            "ok": True,
            "summary": "Read a.py",
            "data": {"path": "a.py", "content": "print('hi')"},
        }, 4)
        segment = await context.get_raw_segment("s1", 4, 4)
        artifact = [item for item in segment if item["kind"] == "artifact"][0]
        assert artifact["tool_name"] == "read_file"
        assert artifact["path"] == "a.py"
        assert artifact["step_id"] == 4

    @pytest.mark.asyncio
    async def test_get_raw_segment_filters_steps_and_artifacts(self):
        context = _make_context()
        await context.append_step_event("s1", "t1", 1, {"summary": "one"})
        await context.append_step_event("s1", "t1", 5, {"summary": "five"})
        await context.append_artifact_event("s1", {"kind": "manual", "step_id": 5})
        segment = await context.get_raw_segment("s1", 2, 5)
        assert all(item["kind"] != "step" or item["step_id"] == 5 for item in segment)
        assert any(item["kind"] == "artifact" and item["step_id"] == 5 for item in segment)
