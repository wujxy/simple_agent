from simple_agent.planner import Planner
from simple_agent.llm.base import BaseLLMClient


class MockLLM(BaseLLMClient):
    def __init__(self, response: str):
        self._response = response

    def generate(self, prompt: str) -> str:
        return self._response

    def generate_with_messages(self, messages: list[dict]) -> str:
        return self._response


class TestPlanner:
    def test_generate_plan(self):
        llm = MockLLM('{"goal": "read file", "steps": [{"id": "1", "title": "Read the file", "description": "Read the target file"}], "summary": "Read the file"}')
        planner = Planner(llm)
        plan = planner.generate_plan("Read README.md")
        assert plan.goal == "read file"
        assert len(plan.steps) == 1
        assert plan.steps[0].title == "Read the file"
        assert plan.steps[0].status == "pending"

    def test_fallback_on_bad_json(self):
        llm = MockLLM("not json")
        planner = Planner(llm)
        plan = planner.generate_plan("Do something")
        assert plan.goal == "Do something"
        assert len(plan.steps) == 1
        assert "fallback" in (plan.summary or "").lower()

    def test_needs_planning_simple(self):
        llm = MockLLM("")
        planner = Planner(llm)
        assert planner.needs_planning("Read the file config.yaml") is False
        assert planner.needs_planning("Create a new project with tests and docs") is True
