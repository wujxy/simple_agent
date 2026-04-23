from simple_agent.context.context_layers import PromptContext


class TestPromptContext:
    def test_creation(self):
        pc = PromptContext(
            execution_state="mode=running, step=1/20",
            prompt_memory_block="[user] hello",
        )
        assert pc.execution_state == "mode=running, step=1/20"
        assert pc.prompt_memory_block == "[user] hello"

    def test_to_dict(self):
        pc = PromptContext(
            execution_state="state",
            prompt_memory_block="memory",
        )
        d = pc.to_dict()
        assert set(d.keys()) == {
            "objective_block",
            "execution_state",
            "artifact_snapshot",
            "next_decision_point",
            "prompt_memory_block",
        }
        assert d["objective_block"] == ""
        assert d["artifact_snapshot"] == ""
        assert d["next_decision_point"] == ""
        assert d["prompt_memory_block"] == "memory"
