from simple_agent.context.context_layers import PromptContext
from simple_agent.engine.prompt_service import PromptService
from simple_agent.engine.query_state import QueryState
from simple_agent.engine.verifier import Verifier
from simple_agent.prompts.action_prompt import build_context_prompt


class _DummyLLM:
    async def generate(self, prompt: str) -> str:
        return '{"complete": true, "reason": "ok", "missing": []}'


def test_action_prompt_renders_only_new_context_blocks():
    ctx = PromptContext(
        objective_block="User objective",
        execution_state="mode=running",
        prompt_memory_block="[step 1] done",
        artifact_snapshot="File snapshots:\na.py",
        next_decision_point="Next decision",
    )
    prompt = build_context_prompt(ctx)
    assert "Memory:\n[step 1] done" in prompt
    assert "Confirmed facts" not in prompt
    assert "Working set" not in prompt
    assert "Recent observations" not in prompt
    assert "Context summary" not in prompt


def test_summary_prompt_uses_prompt_memory_block():
    service = PromptService()
    state = QueryState(session_id="s1", turn_id="t1", user_message="summarize")
    ctx = PromptContext(prompt_memory_block="[system] progress")
    prompt = service.build_summary_prompt(state, ctx)
    assert "[system] progress" in prompt


def test_verifier_uses_prompt_memory_block_not_legacy_fields():
    verifier = Verifier(_DummyLLM())
    ctx = PromptContext(
        objective_block="Objective",
        execution_state="Execution",
        prompt_memory_block="Memory block",
        artifact_snapshot="Artifact",
    )
    evidence = verifier._format_context(ctx)
    assert "=== Memory ===\nMemory block" in evidence
    assert "Confirmed Facts" not in evidence
    assert "Working Set" not in evidence
    assert "Session Memory" not in evidence
