import pytest

from simple_agent.parser import ActionParser, ParseError


def test_valid_tool_call():
    parser = ActionParser()
    action = parser.parse('{"type": "tool_call", "reason": "need info", "tool": "read_file", "args": {"path": "test.txt"}}')
    assert action.type == "tool_call"
    assert action.tool == "read_file"
    assert action.args == {"path": "test.txt"}


def test_valid_finish():
    parser = ActionParser()
    action = parser.parse('{"type": "finish", "reason": "done", "message": "Task complete"}')
    assert action.type == "finish"
    assert action.message == "Task complete"


def test_valid_ask_user():
    parser = ActionParser()
    action = parser.parse('{"type": "ask_user", "reason": "unclear", "message": "What file?"}')
    assert action.type == "ask_user"
    assert action.message == "What file?"


def test_malformed_json():
    parser = ActionParser()
    with pytest.raises(ParseError):
        parser.parse("this is not json at all")


def test_missing_type_field():
    parser = ActionParser()
    with pytest.raises(ParseError):
        parser.parse('{"tool": "read_file"}')


def test_tool_call_without_tool():
    parser = ActionParser()
    with pytest.raises(ParseError):
        parser.parse('{"type": "tool_call", "reason": "need info"}')


def test_finish_without_message():
    parser = ActionParser()
    with pytest.raises(ParseError):
        parser.parse('{"type": "finish", "reason": "done"}')


def test_json_wrapped_in_prose():
    parser = ActionParser()
    text = 'Here is the action: {"type": "finish", "reason": "done", "message": "Done!"}'
    action = parser.parse(text)
    assert action.type == "finish"


def test_json_in_code_fence():
    parser = ActionParser()
    text = '```json\n{"type": "finish", "reason": "done", "message": "Done!"}\n```'
    action = parser.parse(text)
    assert action.type == "finish"


def test_safe_parse_returns_none_on_failure():
    parser = ActionParser()
    assert parser.safe_parse("not json") is None


def test_safe_parse_returns_action_on_success():
    parser = ActionParser()
    action = parser.safe_parse('{"type": "finish", "reason": "ok", "message": "done"}')
    assert action is not None
    assert action.type == "finish"


def test_arguments_field_alias():
    parser = ActionParser()
    action = parser.parse('{"type": "tool_call", "reason": "test", "tool": "bash", "arguments": {"command": "ls"}}')
    assert action.args == {"command": "ls"}
