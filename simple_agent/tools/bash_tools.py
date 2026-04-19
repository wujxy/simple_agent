from __future__ import annotations

import asyncio

from simple_agent.tools.base import BaseTool


class BashTool(BaseTool):
    name = "bash"
    description = "Run a shell command and return stdout, stderr, and return code"
    args_schema = {"command": "string - the shell command to run"}

    async def run(self, *, command: str, **_kwargs) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            parts: list[str] = []
            if stdout:
                parts.append(f"stdout:\n{stdout.decode().strip()}")
            if stderr:
                parts.append(f"stderr:\n{stderr.decode().strip()}")
            parts.append(f"return code: {proc.returncode}")
            return "\n".join(parts)
        except asyncio.TimeoutError:
            return "Error: Command timed out after 30 seconds."
        except Exception as e:
            return f"Error running command: {e}"
