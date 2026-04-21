from __future__ import annotations

import json
import os

from simple_agent.tools.base import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the content of a text file"
    args_schema = {"path": "string - path to the file"}

    async def run(self, *, path: str, **_kwargs) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            line_count = content.count("\n") + 1
            return json.dumps({
                "status": "success",
                "path": path,
                "lines": line_count,
                "content": content,
                "summary": f"File '{path}' read successfully ({line_count} lines).",
            }, ensure_ascii=False)
        except FileNotFoundError:
            return f"Error: File '{path}' not found."
        except Exception as e:
            return f"Error reading '{path}': {e}"


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a text file"
    args_schema = {"path": "string - file path", "content": "string - content to write"}

    async def run(self, *, path: str, content: str, **_kwargs) -> str:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

            is_new = not os.path.exists(path)
            old_lines: list[str] = []
            if not is_new:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        old_lines = f.read().splitlines(keepends=True)
                except Exception:
                    is_new = True

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            new_lines = content.splitlines(keepends=True)
            op = "created" if is_new else "updated"

            # Count changes via diff
            import difflib
            diff_lines = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{path}", tofile=f"b/{path}",
                n=0,
            ))
            added = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
            removed = sum(1 for l in diff_lines if l.startswith('-') and not l.startswith('---'))

            return json.dumps({
                "status": "success",
                "path": path,
                "operation": op,
                "lines_written": len(new_lines),
                "lines_added": added,
                "lines_removed": removed,
                "summary": f"File '{path}' was {op} successfully. "
                           f"The file now exactly matches the content you supplied "
                           f"({added} lines added, {removed} removed).",
                "fact": f"{path} now exactly matches the content you supplied in this call.",
            }, ensure_ascii=False)
        except Exception as e:
            return f"Error writing to '{path}': {e}"


class ListDirTool(BaseTool):
    name = "list_dir"
    description = "List files and directories in a given path"
    args_schema = {"path": "string - directory path"}

    async def run(self, *, path: str, **_kwargs) -> str:
        try:
            entries = sorted(os.listdir(path))
            if not entries:
                return f"(empty directory: {path})"
            return "\n".join(entries)
        except FileNotFoundError:
            return f"Error: Directory '{path}' not found."
        except Exception as e:
            return f"Error listing '{path}': {e}"
