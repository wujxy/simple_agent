import time

import pytest

from simple_agent.context.context_layers import PromptContext
from simple_agent.context.context_service import ContextService
from simple_agent.engine.query_state import QueryState
from simple_agent.memory.compact_service import CompactService
from simple_agent.memory.memory_service import MemoryService
from simple_agent.memory.memory_store import MemoryStore
from simple_agent.prompts.action_prompt import build_context_prompt
from simple_agent.sessions.schemas import SessionState, TurnState


def _make_services(char_budget: int = 12000) -> tuple[MemoryService, ContextService]:
    store = MemoryStore()
    compact = CompactService(char_budget=char_budget, trigger_ratio=0.5, hot_keep_last=2, min_candidates=4)
    memory = MemoryService(store, compact_service=compact)
    return memory, ContextService(memory)


class TestContextMemoryIntegration:
    @pytest.mark.asyncio
    async def test_build_context_produces_prompt_memory_block(self):
        memory, context = _make_services()
        await memory.record_user_message("s1", "Read test.py and summarize it")
        await memory.record_step_event("s1", {
            "step": 1,
            "action_type": "tool_call",
            "tool_name": "read_file",
            "ok": True,
            "summary": "Read test.py",
            "facts": ["test.py is a Python module"],
        })

        session = SessionState(session_id="s1", created_at=time.time())
        turn = TurnState(turn_id="t1", session_id="s1", user_message="test")
        state = QueryState(session_id="s1", turn_id="t1", user_message="test")
        state.step_count = 1

        prompt_ctx = await context.build_context(session, turn, state)
        assert isinstance(prompt_ctx, PromptContext)
        assert "Read test.py" in prompt_ctx.prompt_memory_block
        assert "step 1" in prompt_ctx.prompt_memory_block
        assert not hasattr(prompt_ctx, "compact_memory_summary")
        assert not hasattr(prompt_ctx, "working_set_summary")
        assert not hasattr(prompt_ctx, "recent_observations")
        assert not hasattr(prompt_ctx, "confirmed_facts")

    def test_action_prompt_places_memory_before_artifact_snapshot(self):
        ctx = PromptContext(
            objective_block="User objective:\n- test",
            execution_state="mode=running",
            prompt_memory_block="[user] hello",
            artifact_snapshot="File snapshots:\na.py",
            next_decision_point="Next decision",
        )
        prompt = build_context_prompt(ctx)
        assert prompt.index("Memory:") < prompt.index("File snapshots:")

    @pytest.mark.asyncio
    async def test_low_budget_triggers_compact_through_memory_service(self):
        memory, _context = _make_services(char_budget=4000)
        for i in range(40):
            await memory.record_step_event("s1", {
                "step": i + 1,
                "action_type": "tool_call",
                "tool_name": "read_file",
                "ok": True,
                "summary": f"Read file {i} with enough detail to make memory grow quickly",
                "facts": [f"fact {i}"],
            })

        block = await memory.build_prompt_memory("s1", current_step=12)
        assert "[compacted summary]" in block
        assert any(item.get("state") == "compacted" for item in memory._store.get_all("s1"))
