from __future__ import annotations

import difflib
import os

from simple_agent.tools.base import BaseTool


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the content of a text file"
    args_schema = {"path": "string - path to the file"}

    async def run(self, *, path: str, **_kwargs) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
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

            # Read old content for diff
            old_lines: list[str] = []
            is_new = not os.path.exists(path)
            if not is_new:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        old_lines = f.read().splitlines(keepends=True)
                except Exception:
                    is_new = True

            # Write new content
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            new_lines = content.splitlines(keepends=True)
            op = "created" if is_new else "updated"

            # Generate unified diff
            diff_lines = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{path}", tofile=f"b/{path}",
                n=2,
            ))

            # Count changes
            added = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
            removed = sum(1 for l in diff_lines if l.startswith('-') and not l.startswith('---'))

            diff_text = ''.join(diff_lines)

            # Threshold: if diff is small enough, show full; otherwise truncate
            max_diff_lines = 50
            diff_as_lines = diff_text.splitlines(keepends=True)
            if len(diff_as_lines) <= max_diff_lines:
                preview = diff_text
            else:
                preview = ''.join(diff_as_lines[:max_diff_lines])
                preview += f"... (diff truncated, showing first {max_diff_lines} of {len(diff_as_lines)} lines, +{added}/-{removed} total)\n"

            return f"Successfully wrote to '{path}' ({op}, +{added}/-{removed} lines).\n{preview}"
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
