from simple_agent.tools.core.types import ToolCapabilities, ToolSpec

BashSpec = ToolSpec(
    name="bash",
    description="Run a shell command and return stdout, stderr, and exit code",
    family="shell",
    capabilities=ToolCapabilities(
        read_only=False,
        idempotent=False,
        mutates_files=True,
        requires_approval=True,
        preferred_after_write=True,
    ),
    input_schema={
        "command": "string (required) — the shell command to run",
        "timeout": "int (optional, default 30, max 300) — command timeout in seconds",
    },
    output_schema={
        "exit_code": "int — process exit code",
        "stdout": "string — standard output",
        "stderr": "string — standard error",
    },
    guarantees=[
        "on success (exit code 0), stdout and stderr contain the full command output",
        "on error (non-zero exit), data contains exit_code, stdout, and stderr",
    ],
    short_prompt="bash(command, timeout?)",
    detail_prompt=(
        "Purpose: run a shell command.\n"
        "Returns: success (exit 0) / error (non-zero exit).\n"
        "Guarantee: data contains exit_code, stdout, stderr.\n"
        "Use this to verify your work (run tests, check output) rather than re-reading files."
    ),
)
