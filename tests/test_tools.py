import asyncio

from simple_agent.tools.bash_tool import BashTool
from simple_agent.tools.list_dir import ListDirTool
from simple_agent.tools.read_file import ReadFileTool
from simple_agent.tools.write_file import WriteFileTool
from simple_agent.tools.registry import ToolRegistry


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestReadFileTool:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")

        tool = ReadFileTool()
        result = run(tool.run(path=str(f)))
        assert result.status == "success"
        assert result.data["content"] == "hello world"
        assert result.data["lines"] == 1

    def test_read_missing_file(self):
        tool = ReadFileTool()
        result = run(tool.run(path="/nonexistent/file.txt"))
        assert result.status == "error"
        assert "not found" in result.error


class TestWriteFileTool:
    def test_write_new_file(self, tmp_path):
        target = tmp_path / "out.txt"
        tool = WriteFileTool()
        result = run(tool.run(path=str(target), content="written content"))
        assert result.status == "success"
        assert result.data["operation"] == "created"
        assert target.read_text() == "written content"

    def test_write_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "out.txt"
        tool = WriteFileTool()
        result = run(tool.run(path=str(target), content="nested"))
        assert result.status == "success"
        assert target.read_text() == "nested"


class TestListDirTool:
    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        tool = ListDirTool()
        result = run(tool.run(path=str(tmp_path)))
        assert result.status == "success"
        assert "a.txt" in result.data["entries"]
        assert "b.txt" in result.data["entries"]

    def test_list_empty_directory(self, tmp_path):
        tool = ListDirTool()
        result = run(tool.run(path=str(tmp_path)))
        assert result.status == "success"
        assert result.data["entries"] == []

    def test_list_missing_directory(self):
        tool = ListDirTool()
        result = run(tool.run(path="/nonexistent/dir"))
        assert result.status == "error"
        assert "not found" in result.error


class TestBashTool:
    def test_bash_echo(self):
        tool = BashTool()
        result = run(tool.run(command="echo hello"))
        assert result.status == "success"
        assert "hello" in result.data["stdout"]
        assert result.data["exit_code"] == 0

    def test_bash_failing_command(self):
        tool = BashTool()
        result = run(tool.run(command="false"))
        assert result.status == "error"
        assert result.data["exit_code"] != 0


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
