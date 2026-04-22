import pytest
from simple_agent.context.context_layers import WorkingSet, PromptContext
from simple_agent.memory.memory_store import MemoryStore
from simple_agent.memory.memory_service import MemoryService, SessionSummaryService


class TestWorkingSet:
    def test_record_read(self):
        ws = WorkingSet()
        ws.record_read("a.py")
        ws.record_read("b.py")
        ws.record_read("a.py")  # duplicate ignored
        assert ws.recently_read_files == ["a.py", "b.py"]

    def test_record_write(self):
        ws = WorkingSet()
        ws.record_write("out.txt")
        assert ws.recently_written_files == ["out.txt"]

    def test_active_files(self):
        ws = WorkingSet()
        ws.record_read("a.py")
        ws.record_write("b.py")
        assert set(ws.active_files) == {"a.py", "b.py"}

    def test_record_action_detects_repeat(self):
        ws = WorkingSet()
        ws.record_action({"tool": "read_file", "args": {"path": "a.py"}})
        ws.record_action({"tool": "read_file", "args": {"path": "a.py"}})
        assert len(ws.repeated_actions) == 1
        assert ws.repeated_actions[0]["count"] == 2

    def test_summarize(self):
        ws = WorkingSet()
        ws.record_read("a.py")
        ws.record_write("b.py")
        s = ws.summarize()
        assert "a.py" in s["recently_read"]
        assert "b.py" in s["recently_written"]


class TestPromptContext:
    def test_creation(self):
        pc = PromptContext(
            execution_state="mode=running, step=1/20",
            working_set_summary="Read: a.py",
            compact_memory_summary="(no prior context)",
            recent_observations="Last tool: read_file ok",
        )
        assert pc.execution_state == "mode=running, step=1/20"
        assert pc.working_set_summary == "Read: a.py"

    def test_to_dict(self):
        pc = PromptContext(
            execution_state="state",
            working_set_summary="ws",
            compact_memory_summary="summary",
            recent_observations="obs",
        )
        d = pc.to_dict()
        assert set(d.keys()) == {
            "objective_block",
            "execution_state",
            "artifact_snapshot",
            "confirmed_facts",
            "next_decision_point",
            "compact_memory_summary",
            "working_set_summary",
            "recent_observations",
        }
        assert d["objective_block"] == ""
        assert d["artifact_snapshot"] == ""
        assert d["next_decision_point"] == ""


class TestSessionSummaryService:
    @pytest.fixture
    def services(self):
        store = MemoryStore()
        ms = MemoryService(store)
        ss = SessionSummaryService(ms)
        return ms, ss

    @pytest.mark.asyncio
    async def test_empty_session_returns_no_context(self, services):
        ms, ss = services
        result = await ss.get_compact_summary("sess_1")
        assert result == "(no prior context)"

    @pytest.mark.asyncio
    async def test_system_notes_are_summarized(self, services):
        ms, ss = services
        await ms.add_system_note("sess_1", "Plan created: write a program")
        await ms.add_system_note("sess_1", "write_file(f.py) -> Successfully wrote")
        result = await ss.get_compact_summary("sess_1")
        assert "Plan created" in result
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_deduplicates_repeated_reads(self, services):
        ms, ss = services
        for _ in range(5):
            await ms.add_system_note("sess_1", "read_file({'path': 'f.py'}) -> file content here")
        result = await ss.get_compact_summary("sess_1")
        assert result.count("read_file") <= 2
