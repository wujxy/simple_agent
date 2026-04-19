from __future__ import annotations

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
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to '{path}'."
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
