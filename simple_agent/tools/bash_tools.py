from __future__ import annotations

import subprocess

from simple_agent.tools.base import BaseTool


class BashTool(BaseTool):
    name = "bash"
    description = "Run a shell command and return stdout, stderr, and return code"
    args_schema = {"command": "string - the shell command to run"}

    def run(self, *, command: str, **_kwargs) -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            parts: list[str] = []
            if result.stdout:
                parts.append(f"stdout:\n{result.stdout.strip()}")
            if result.stderr:
                parts.append(f"stderr:\n{result.stderr.strip()}")
            parts.append(f"return code: {result.returncode}")
            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 30 seconds."
        except Exception as e:
            return f"Error running command: {e}"
