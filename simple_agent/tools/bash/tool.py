from __future__ import annotations

import asyncio

from simple_agent.tools.core.base import BaseTool
from simple_agent.tools.core.types import ToolObservation
from simple_agent.tools.bash.schemas import BashInput
from simple_agent.tools.bash.spec import BashSpec


class BashTool(BaseTool):
    spec = BashSpec
    input_model = BashInput

    async def run(self, tool_input: BashInput, ctx: dict | None = None) -> ToolObservation:
        command = tool_input.command
        timeout = tool_input.timeout

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            return ToolObservation(
                ok=False, status="error",
                error=f"Command timed out after {timeout}s.",
                retryable=True,
                memory={
                    "summary": f"$ {command} timed out after {timeout}s.",
                    "errors": [f"Command timed out after {timeout}s."],
                },
                diagnostics={"timeout": True, "timeout_seconds": timeout},
            )
        except Exception as e:
            return ToolObservation(ok=False, status="error", error=f"Error running command: {e}")

        stdout_text = stdout.decode().strip() if stdout else ""
        stderr_text = stderr.decode().strip() if stderr else ""
        exit_code = proc.returncode

        if exit_code == 0:
            return ToolObservation(
                ok=True,
                status="success",
                summary=f"Command exited with code 0.",
                facts=[f"Command '{command}' executed successfully (exit code 0)."],
                data={
                    "command": command,
                    "exit_code": exit_code,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                },
                memory={
                    "summary": f"$ {command} -> exit 0",
                    "facts": [f"Command succeeded: {command}"],
                },
                artifacts={
                    "kind": "shell_result",
                    "command": command,
                    "exit_code": exit_code,
                    "stdout_preview": stdout_text[:1000],
                    "stderr_preview": stderr_text[:800],
                },
                display={"stdout_preview": stdout_text[:1000], "stderr_preview": stderr_text[:800]},
                diagnostics={"timeout": False},
            )
        else:
            error_summary = stderr_text[:500] or stdout_text[:500] or f"exit code {exit_code}"
            return ToolObservation(
                ok=False,
                status="error",
                summary=f"Command failed with exit code {exit_code}.",
                error=f"exit code {exit_code}: {stderr_text[:300]}",
                data={
                    "command": command,
                    "exit_code": exit_code,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                },
                retryable=True,
                memory={
                    "summary": f"$ {command} -> exit {exit_code}: {error_summary}",
                    "errors": [error_summary],
                },
                artifacts={
                    "kind": "shell_result",
                    "command": command,
                    "exit_code": exit_code,
                    "stdout_preview": stdout_text[:1000],
                    "stderr_preview": stderr_text[:800],
                },
                display={"stdout_preview": stdout_text[:1000], "stderr_preview": stderr_text[:800]},
                diagnostics={"timeout": False, "error_summary": error_summary},
            )
