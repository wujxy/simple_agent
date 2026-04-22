from __future__ import annotations


_PLAN_SCHEMA = """Required JSON format:
{
  "overview": "one-line description of what the agent will accomplish",
  "deliverables": ["expected output files or artifacts"],
  "likely_files": ["files the agent will probably touch"],
  "verification_targets": ["what to verify to confirm success"],
  "steps": [
    {
      "step_id": "S1",
      "title": "short step title",
      "purpose": "why this step exists",
      "action_type": "inspect|read|modify|run|verify|finalize",
      "target_files": ["relevant files, if any"],
      "entry_conditions": ["what must be true before starting"],
      "completion_criteria": ["what proves this step is done"],
      "preferred_tools": ["suggested tools for this step"]
    }
  ]
}"""

_PLAN_RULES = """Plan design rules:
1. Every step must describe what the AGENT should do, not what the target program should do internally.
2. action_type semantics:
   - inspect: discover project state, file existence, candidate targets (use list_dir, check existence)
   - read: retrieve known file content for reasoning (use read_file)
   - modify: create or update source files (use write_file)
   - run: execute a command (use bash)
   - verify: check output/artifact correctness (use verify action or bash)
   - finalize: confirm task is complete
3. Steps with action_type "modify" must specify target_files.
4. Every step must have at least one completion_criteria.
5. The plan must end with a verify or finalize step.
6. 2-6 steps is usually enough. Trivial tasks may use 1 step.

Example for "Create a Gaussian fitting script and plot":
{
  "overview": "Create and verify a Gaussian fitting script that produces a plot",
  "deliverables": ["gaussian_fit.py", "output plot image"],
  "likely_files": ["gaussian_fit.py"],
  "verification_targets": ["script runs successfully", "plot file is generated"],
  "steps": [
    {"step_id": "S1", "action_type": "inspect", "title": "Check workspace", "completion_criteria": ["Know whether gaussian_fit.py already exists"]},
    {"step_id": "S2", "action_type": "modify", "title": "Create gaussian_fit.py", "target_files": ["gaussian_fit.py"], "completion_criteria": ["File contains complete implementation"]},
    {"step_id": "S3", "action_type": "run", "title": "Run the script", "target_files": ["gaussian_fit.py"], "completion_criteria": ["Script exits with code 0"]},
    {"step_id": "S4", "action_type": "verify", "title": "Verify output", "completion_criteria": ["Plot file exists"]}
  ]
}"""


def build_planner_prompt(user_request: str) -> str:
    return f"""You are a planning agent. Create an execution plan for the agent to follow.

The plan must describe what the AGENT should do (inspect, read, modify, run, verify, finalize), NOT what the target program should do internally.

{_PLAN_SCHEMA}

{_PLAN_RULES}

User task: {user_request}

Response (JSON only):"""


def build_replan_prompt(user_request: str, failed_step: str, reason: str, completed_steps: list[str]) -> str:
    completed = "\n".join(f"- {s}" for s in completed_steps) if completed_steps else "(none)"
    return f"""You are a planning agent. The previous plan hit a blocker and needs adjustment.

Original task: {user_request}

Completed steps:
{completed}

Failed step: {failed_step}
Failure reason: {reason}

Create a revised plan starting from where things went wrong.

{_PLAN_SCHEMA}

{_PLAN_RULES}

Response (JSON only):"""
