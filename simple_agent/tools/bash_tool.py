from __future__ import annotations

import asyncio

from simple_agent.schemas import ToolOutput
from simple_agent.tools.base import BaseTool


class BashTool(BaseTool):
    name = "bash"
    description = "Run a shell command and return stdout, stderr, and return code"
    args_schema = {"command": "string - the shell command to run"}

    async def run(self, *, command: str, **_kwargs) -> ToolOutput:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            stdout_text = stdout.decode().strip() if stdout else ""
            stderr_text = stderr.decode().strip() if stderr else ""
            exit_code = proc.returncode

            if exit_code == 0:
                return ToolOutput(
                    status="success",
                    summary=f"Command completed with exit code 0.",
                    facts=[f"Command '{command}' executed successfully (exit code 0)."],
                    data={
                        "command": command, "exit_code": exit_code,
                        "stdout": stdout_text[:2000], "stderr": stderr_text[:500],
                    },
                )
            else:
                return ToolOutput(
                    status="error",
                    summary=f"Command failed with exit code {exit_code}.",
                    error=f"exit code {exit_code}: {stderr_text[:200]}",
                    data={
                        "command": command, "exit_code": exit_code,
                        "stdout": stdout_text[:500], "stderr": stderr_text[:200],
                    },
                )
        except asyncio.TimeoutError:
            return ToolOutput(status="error", error="Command timed out after 30 seconds.")
        except Exception as e:
            return ToolOutput(status="error", error=f"Error running command: {e}")
