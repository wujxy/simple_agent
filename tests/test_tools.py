import os
import tempfile

from simple_agent.tools.bash_tools import BashTool
from simple_agent.tools.file_tools import ListDirTool, ReadFileTool, WriteFileTool
from simple_agent.tools.registry import ToolRegistry


class TestReadFileTool:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")

        tool = ReadFileTool()
        result = tool.run(path=str(f))
        assert result == "hello world"

    def test_read_missing_file(self):
        tool = ReadFileTool()
        result = tool.run(path="/nonexistent/file.txt")
        assert "not found" in result


class TestWriteFileTool:
    def test_write_new_file(self, tmp_path):
        target = tmp_path / "out.txt"
        tool = WriteFileTool()
        result = tool.run(path=str(target), content="written content")
        assert "Successfully" in result
        assert target.read_text() == "written content"

    def test_write_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "out.txt"
        tool = WriteFileTool()
        result = tool.run(path=str(target), content="nested")
        assert "Successfully" in result


class TestListDirTool:
    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        tool = ListDirTool()
        result = tool.run(path=str(tmp_path))
        assert "a.txt" in result
        assert "b.txt" in result

    def test_list_empty_directory(self, tmp_path):
        tool = ListDirTool()
        result = tool.run(path=str(tmp_path))
        assert "empty" in result

    def test_list_missing_directory(self):
        tool = ListDirTool()
        result = tool.run(path="/nonexistent/dir")
        assert "not found" in result


class TestBashTool:
    def test_bash_echo(self):
        tool = BashTool()
        result = tool.run(command="echo hello")
        assert "hello" in result
        assert "return code: 0" in result

    def test_bash_failing_command(self):
        tool = BashTool()
        result = tool.run(command="false")
        assert "return code: 1" in result


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = ReadFileTool()
        registry.register(tool)
        assert registry.get("read_file") is tool

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        assert set(registry.list_tools()) == {"read_file", "write_file"}

    def test_tool_descriptions(self):
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        desc = registry.tool_descriptions_for_prompt()
        assert "read_file" in desc
