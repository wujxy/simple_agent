BASH_PROMPT = """Tool: bash
- Purpose: Run a shell command.
- Input: command (required), timeout (optional, default 30s).
- Output: data contains exit_code, stdout, stderr.
- Guarantees: On exit code 0, the command ran successfully. stdout/stderr contain full output.
- Preferred after write: Use bash to verify your work (run tests, check output) rather than re-reading files.
"""
