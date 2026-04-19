from simple_agent.policy import PolicyChecker
from simple_agent.schemas import AgentAction


class TestPolicy:
    def test_read_allowed_by_default(self):
        policy = PolicyChecker()
        action = AgentAction(type="tool_call", tool="read_file", args={"path": "test.txt"})
        decision = policy.check(action)
        assert decision.allowed is True
        assert not decision.requires_approval

    def test_list_dir_allowed(self):
        policy = PolicyChecker()
        action = AgentAction(type="tool_call", tool="list_dir", args={"path": "."})
        decision = policy.check(action)
        assert decision.allowed is True

    def test_write_requires_approval(self):
        policy = PolicyChecker()
        action = AgentAction(type="tool_call", tool="write_file", args={"path": "out.txt", "content": "x"})
        decision = policy.check(action)
        assert decision.allowed is True
        assert decision.requires_approval is True

    def test_bash_blocked_by_default(self):
        policy = PolicyChecker()
        action = AgentAction(type="tool_call", tool="bash", args={"command": "ls"})
        decision = policy.check(action)
        # allow_bash=False but require_approval_for_bash=True => approval required
        assert decision.allowed is True
        assert decision.requires_approval is True

    def test_blocked_command_pattern(self, tmp_path):
        config = tmp_path / "policy.yaml"
        config.write_text("allow_bash: true\nblocked_commands:\n  - rm -rf\n")
        policy = PolicyChecker(str(config))
        action = AgentAction(type="tool_call", tool="bash", args={"command": "rm -rf /"})
        decision = policy.check(action)
        assert decision.allowed is False
        assert "Blocked" in decision.reason

    def test_non_tool_action_allowed(self):
        policy = PolicyChecker()
        action = AgentAction(type="finish", message="done")
        decision = policy.check(action)
        assert decision.allowed is True

    def test_config_from_file(self, tmp_path):
        config = tmp_path / "policy.yaml"
        config.write_text("allow_write: true\nrequire_approval_for_write: false\n")
        policy = PolicyChecker(str(config))
        action = AgentAction(type="tool_call", tool="write_file", args={"path": "f", "content": "x"})
        decision = policy.check(action)
        assert decision.allowed is True
        assert not decision.requires_approval
