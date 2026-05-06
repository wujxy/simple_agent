import asyncio

from simple_agent.tools.bash import BashTool
from simple_agent.tools.edit_file import EditFileTool
from simple_agent.tools.glob import GlobTool
from simple_agent.tools.grep import GrepTool
from simple_agent.tools.list_dir import ListDirTool
from simple_agent.tools.multi_edit import MultiEditTool
from simple_agent.tools.read_file import ReadFileTool
from simple_agent.tools.write_file import WriteFileTool
from simple_agent.tools.core.registry import ToolRegistry
from simple_agent.tools.read_file.schemas import ReadFileInput
from simple_agent.tools.write_file.schemas import WriteFileInput
from simple_agent.tools.list_dir.schemas import ListDirInput
from simple_agent.tools.bash.schemas import BashInput
from simple_agent.tools.edit_file.schemas import EditFileInput
from simple_agent.tools.glob.schemas import GlobInput
from simple_agent.tools.grep.schemas import GrepInput
from simple_agent.tools.multi_edit.schemas import EditOperation, MultiEditInput


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestReadFileTool:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")

        tool = ReadFileTool()
        result = run(tool.run(ReadFileInput(path=str(f))))
        assert result.status == "success"
        assert result.data["content"] == "hello world"
        assert result.data["total_lines"] == 1
        assert result.memory["references"][0]["path"] == str(f)
        assert result.artifacts["content"] == "hello world"

    def test_read_missing_file(self):
        tool = ReadFileTool()
        result = run(tool.run(ReadFileInput(path="/nonexistent/file.txt")))
        assert result.status == "error"
        assert "not found" in result.error


class TestWriteFileTool:
    def test_write_new_file(self, tmp_path):
        target = tmp_path / "out.txt"
        tool = WriteFileTool()
        result = run(tool.run(WriteFileInput(path=str(target), content="written content")))
        assert result.status == "success"
        assert result.data["operation"] == "created"
        assert target.read_text() == "written content"
        assert result.memory["changed_paths"] == [str(target)]
        assert result.artifacts["kind"] == "write_guarantee"

    def test_write_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "out.txt"
        tool = WriteFileTool()
        result = run(tool.run(WriteFileInput(path=str(target), content="nested")))
        assert result.status == "success"
        assert target.read_text() == "nested"

    def test_write_noop_when_identical(self, tmp_path):
        target = tmp_path / "same.txt"
        target.write_text("same content", encoding="utf-8")
        tool = WriteFileTool()
        result = run(tool.run(WriteFileInput(path=str(target), content="same content")))
        assert result.status == "noop"
        assert "identical" in result.summary.lower()


class TestListDirTool:
    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        tool = ListDirTool()
        result = run(tool.run(ListDirInput(path=str(tmp_path))))
        assert result.status == "success"
        assert "a.txt" in result.data["entries"]
        assert "b.txt" in result.data["entries"]
        assert result.memory["facts"]

    def test_list_empty_directory(self, tmp_path):
        tool = ListDirTool()
        result = run(tool.run(ListDirInput(path=str(tmp_path))))
        assert result.status == "success"
        assert result.data["entries"] == []

    def test_list_missing_directory(self):
        tool = ListDirTool()
        result = run(tool.run(ListDirInput(path="/nonexistent/dir")))
        assert result.status == "error"
        assert "not found" in result.error


class TestBashTool:
    def test_bash_echo(self):
        tool = BashTool()
        result = run(tool.run(BashInput(command="echo hello")))
        assert result.status == "success"
        assert "hello" in result.data["stdout"]
        assert result.data["exit_code"] == 0
        assert result.memory["facts"]

    def test_bash_failing_command(self):
        tool = BashTool()
        result = run(tool.run(BashInput(command="false")))
        assert result.status == "error"
        assert result.data["exit_code"] != 0
        assert result.memory["errors"]


class TestSearchAndEditTools:
    def test_glob_finds_files(self, tmp_path):
        target = tmp_path / "a.py"
        target.write_text("x", encoding="utf-8")
        result = run(GlobTool().run(GlobInput(pattern="**/*.py", root=str(tmp_path))))
        assert result.status == "success"
        assert str(target) in result.data["matches"]

    def test_grep_returns_line_refs(self, tmp_path):
        target = tmp_path / "a.py"
        target.write_text("def foo():\n    pass\n", encoding="utf-8")
        result = run(GrepTool().run(GrepInput(pattern="foo", root=str(tmp_path), include="**/*.py")))
        assert result.status == "success"
        assert result.data["match_count"] == 1
        assert result.memory["references"][0]["start_line"] == 1

    def test_edit_file_replaces_exact_text(self, tmp_path):
        target = tmp_path / "a.py"
        target.write_text("return 1\n", encoding="utf-8")
        result = run(EditFileTool().run(EditFileInput(
            path=str(target), old_text="return 1", new_text="return 2",
        )))
        assert result.status == "success"
        assert target.read_text(encoding="utf-8") == "return 2\n"
        assert result.changed_paths == [str(target)]

    def test_multi_edit_applies_ordered_edits(self, tmp_path):
        target = tmp_path / "a.py"
        target.write_text("a = 1\nb = 2\n", encoding="utf-8")
        result = run(MultiEditTool().run(MultiEditInput(
            path=str(target),
            edits=[
                EditOperation(old_text="a = 1", new_text="a = 10"),
                EditOperation(old_text="b = 2", new_text="b = 20"),
            ],
        )))
        assert result.status == "success"
        assert "a = 10" in target.read_text(encoding="utf-8")
        assert result.changed_paths == [str(target)]


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
