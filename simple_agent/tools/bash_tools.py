from __future__ import annotations

import asyncio
import json

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

            stdout_text = stdout.decode().strip() if stdout else ""
            stderr_text = stderr.decode().strip() if stderr else ""
            exit_code = proc.returncode

            success = exit_code == 0
            summary = f"Command completed with exit code {exit_code}."
            if success:
                fact = f"Command '{command}' executed successfully (exit code 0)."
            else:
                fact = ""
                summary = f"Command failed with exit code {exit_code}."
                if stderr_text:
                    summary += f" stderr: {stderr_text[:200]}"

            return json.dumps({
                "status": "success" if success else "error",
                "command": command,
                "exit_code": exit_code,
                "stdout_summary": stdout_text[:500],
                "stderr_summary": stderr_text[:200],
                "summary": summary,
                "fact": fact,
            }, ensure_ascii=False)
        except asyncio.TimeoutError:
            return "Error: Command timed out after 30 seconds."
        except Exception as e:
            return f"Error running command: {e}"
