import pytest

from simple_agent.memory.compact_service import CompactService


def _make_items(n: int, start_step: int = 1, kind: str = "step") -> list[dict]:
    items = []
    for i in range(n):
        step = start_step + i
        items.append({
            "id": f"mem_step_{step}",
            "kind": kind,
            "state": "hot",
            "priority": "normal",
            "created_at_step": step,
            "content": f"Step {step} did something important. " * 4,
            "summary": f"Step {step} summary",
            "facts": [f"fact from step {step}"],
            "changed_paths": [f"/tmp/file_{step}.py"] if step % 2 == 0 else [],
            "errors": [],
            "decisions": [],
            "verification": [],
        })
    return items


class TestCompactService:
    @pytest.mark.asyncio
    async def test_no_compact_when_under_budget(self):
        svc = CompactService(char_budget=5000)
        items = _make_items(4)
        result = await svc.maybe_compact(items, current_step=4)
        assert result["did_compact"] is False
        assert result["new_items"] is items

    @pytest.mark.asyncio
    async def test_no_compact_when_too_few_candidates(self):
        svc = CompactService(char_budget=1, trigger_ratio=1.0, hot_keep_last=8)
        items = _make_items(5)
        result = await svc.maybe_compact(items, current_step=5)
        assert result["did_compact"] is False

    @pytest.mark.asyncio
    async def test_compact_replaces_old_hot_with_summary(self):
        svc = CompactService(char_budget=2000, trigger_ratio=0.75, hot_keep_last=2)
        result = await svc.maybe_compact(_make_items(10), current_step=10)
        assert result["did_compact"] is True
        assert result["replaced_count"] == 8

        new_items = result["new_items"]
        assert len([i for i in new_items if i.get("state") == "compacted"]) == 1
        assert len([i for i in new_items if i.get("state") == "hot"]) == 2

    @pytest.mark.asyncio
    async def test_compact_summary_has_source_range(self):
        svc = CompactService(char_budget=2000, trigger_ratio=0.75, hot_keep_last=2)
        result = await svc.maybe_compact(_make_items(10), current_step=10)
        summary = [i for i in result["new_items"] if i.get("state") == "compacted"][0]
        assert summary["kind"] == "summary"
        assert summary["created_at_step"] == 10
        assert summary["source_range"] == {"from_step": 1, "to_step": 8}
        assert "Completed:" in summary["content"]
        assert "Facts:" in summary["content"]

    @pytest.mark.asyncio
    async def test_eviction_when_still_over_budget(self):
        svc = CompactService(char_budget=250, trigger_ratio=0.5, hot_keep_last=2)
        items = _make_items(12)
        items.insert(0, {
            "id": "mem_old_summary",
            "kind": "summary",
            "state": "compacted",
            "priority": "normal",
            "created_at_step": 0,
            "content": "Old compacted summary. " * 30,
            "summary": "Old compacted summary",
        })
        result = await svc.maybe_compact(items, current_step=12)
        assert result["evicted_count"] >= 1

    @pytest.mark.asyncio
    async def test_no_eviction_of_hot_items(self):
        svc = CompactService(char_budget=50, trigger_ratio=0.5, hot_keep_last=2)
        result = await svc.maybe_compact(_make_items(10), current_step=10)
        for item in result["new_items"]:
            if item.get("state") == "hot":
                assert item["id"].startswith("mem_step_")

    def test_estimate_chars(self):
        svc = CompactService()
        items = [{"content": "abc"}, {"summary": "def", "facts": ["gh"]}]
        assert svc._estimate_chars(items) == 8
