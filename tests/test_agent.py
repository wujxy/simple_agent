from simple_agent.agent import SimpleAgent
from simple_agent.llm.base import BaseLLMClient
from simple_agent.policy import PolicyChecker


# A mock LLM that returns a sequence of responses
class SequenceMockLLM(BaseLLMClient):
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._index = 0

    def generate(self, prompt: str) -> str:
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        return '{"type": "finish", "reason": "no more responses", "message": "done"}'

    def generate_with_messages(self, messages: list[dict]) -> str:
        return self.generate("")


class TestSimpleAgent:
    def test_basic_task_loop(self, tmp_path):
        # Plan -> verify -> summary = 3 calls before the action call
        # With enable_planning=False, we skip the plan step
        # Action: finish with a message, then verify, then summary
        responses = [
            # Action: finish
            '{"type": "finish", "reason": "simple task", "message": "The answer is 42"}',
            # Verify
            '{"complete": true, "reason": "done", "missing": null}',
            # Summary
            '{"summary": "Answered the question", "outputs": ["42"], "issues": []}',
        ]
        llm = SequenceMockLLM(responses)
        policy = PolicyChecker()
        policy._rules["allow_read"] = True

        agent = SimpleAgent(
            llm=llm,
            policy=policy,
            max_steps=5,
            enable_planning=False,
        )
        result = agent.run("What is the meaning of life?")
        assert "42" in result or "Answered" in result

    def test_tool_call_flow(self, tmp_path):
        # Write a test file
        test_file = tmp_path / "hello.txt"
        test_file.write_text("hello from test", encoding="utf-8")

        responses = [
            # Action: tool_call read_file
            '{"type": "tool_call", "reason": "need to read", "tool": "read_file", "args": {"path": "'
            + str(test_file)
            + '"}}',
            # Action: finish
            '{"type": "finish", "reason": "done", "message": "File contains: hello from test"}',
            # Verify
            '{"complete": true, "reason": "done", "missing": null}',
            # Summary
            '{"summary": "Read the file", "outputs": ["hello from test"], "issues": []}',
        ]
        llm = SequenceMockLLM(responses)
        policy = PolicyChecker()

        agent = SimpleAgent(
            llm=llm,
            policy=policy,
            max_steps=5,
            enable_planning=False,
        )
        result = agent.run("Read hello.txt")
        assert result is not None
