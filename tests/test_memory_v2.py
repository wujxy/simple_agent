import pytest

from simple_agent.memory.compact_service import CompactService
from simple_agent.memory.memory_service import MemoryService
from simple_agent.memory.memory_store import MemoryStore


class TestMemoryStoreV2:
    def test_replace_all(self):
        store = MemoryStore()
        store.add("s1", {"role": "user", "content": "a"})
        store.add("s1", {"role": "user", "content": "b"})
        store.replace_all("s1", [{"role": "system", "content": "compacted"}])
        assert store.get_all("s1") == [{"role": "system", "content": "compacted"}]

    def test_replace_all_empty_session(self):
        store = MemoryStore()
        store.replace_all("s1", [{"role": "system", "content": "x"}])
        assert len(store.get_all("s1")) == 1

    def test_count(self):
        store = MemoryStore()
        assert store.count("s1") == 0
        store.add("s1", {"content": "a"})
        store.add("s1", {"content": "b"})
        assert store.count("s1") == 2


class TestMemoryServiceV2:
    def _make_service(self, compact: CompactService | None = None) -> MemoryService:
        return MemoryService(MemoryStore(), compact_service=compact)

    @pytest.mark.asyncio
    async def test_record_user_system_tool_step_and_verify_items(self):
        svc = self._make_service()
        await svc.record_user_message("s1", "hello", step=1)
        await svc.add_system_note("s1", "system note", step=1)
        await svc.record_tool_result("s1", "t1", {
            "tool_name": "read_file",
            "ok": True,
            "status": "success",
            "summary": "Read /tmp/a.py",
            "facts": ["File exists"],
            "changed_paths": [],
        }, step=2)
        await svc.record_step_event("s1", {
            "step": 2,
            "action_type": "tool_call",
            "tool_name": "read_file",
            "args": {"path": "/tmp/a.py"},
            "ok": True,
            "summary": "Read /tmp/a.py",
            "facts": ["File exists"],
        })
        await svc.record_verify_result("s1", {
            "step": 3,
            "complete": False,
            "missing": "Need tests",
            "reason": "No verification yet",
        })

        items = svc._store.get_all("s1")
        assert [item["kind"] for item in items] == ["user", "system", "tool", "step", "verify"]
        for item in items:
            assert item["id"].startswith(f"mem_{item['kind']}_{item['created_at_step']}_")
            assert item["state"] == "hot"
            assert item["priority"] == "normal"

    @pytest.mark.asyncio
    async def test_build_prompt_memory_renders_useful_lines(self):
        svc = self._make_service()
        await svc.record_step_event("s1", {
            "step": 1,
            "action_type": "tool_call",
            "tool_name": "write_file",
            "ok": False,
            "summary": "Write failed",
            "changed_paths": ["/tmp/a.py"],
            "errors": ["permission denied"],
            "verification": ["not complete"],
        })

        block = await svc.build_prompt_memory("s1", current_step=1)
        assert "[step 1] tool_call -> write_file(FAILED)" in block
        assert "modified: /tmp/a.py" in block
        assert "error: permission denied" in block
        assert "verification: not complete" in block

    @pytest.mark.asyncio
    async def test_build_prompt_memory_triggers_compact_and_writeback(self):
        compact = CompactService(char_budget=1200, trigger_ratio=0.4, hot_keep_last=2, min_candidates=4)
        svc = self._make_service(compact)
        for i in range(10):
            await svc.record_step_event("s1", {
                "step": i + 1,
                "action_type": "tool_call",
                "tool_name": "read_file",
                "ok": True,
                "summary": f"Read file {i} with enough detail to exceed budget",
                "facts": [f"fact {i}"],
            })

        block = await svc.build_prompt_memory("s1", current_step=10)
        assert "[compacted summary]" in block
        assert len([i for i in svc._store.get_all("s1") if i.get("state") == "compacted"]) >= 1

    @pytest.mark.asyncio
    async def test_get_recent_still_works(self):
        svc = self._make_service()
        await svc.add_system_note("s1", "a")
        await svc.add_system_note("s1", "b")
        recent = await svc.get_recent("s1", limit=1)
        assert len(recent) == 1
        assert recent[0]["content"] == "b"
