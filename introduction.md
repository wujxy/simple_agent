# Agent Loop Implementation

This document outlines the core logic of the `SimpleAgent` loop implemented in `simple_agent/agent.py`.

## Overview
The `SimpleAgent` is designed to autonomously complete tasks by interacting with an LLM, executing tools, and managing state. The lifecycle of an agent run is managed by the `run(task: str)` method.

## Initialization
Before the loop begins, the agent initializes several key components:
- **LLM Client**: Handles communication with the language model (e.g., ZhipuClient).
- **Tool Registry**: Registers available tools (ReadFile, WriteFile, ListDir, Bash).
- **Executor**: Responsible for executing tool calls.
- **Policy Checker**: Validates tool calls against security policies.
- **Memory**: Maintains a sliding window of conversation history and tool outputs.

## The Agent Loop

The execution flow consists of three main phases: Planning, Execution, and Conclusion.

### 1. Planning Phase
If planning is enabled (`enable_planning=True`) and the task complexity warrants it:
1. The agent transitions to the `planning` state.
2. The `Planner` generates a high-level plan consisting of steps.
3. The plan is stored in the `StateManager` and added to memory as context.

### 2. Execution Loop
The core loop runs as long as the state is not terminal and the step limit (`max_steps`) has not been reached.

**A. Step Management**
- The step counter is incremented.
- If a plan exists, the agent identifies the next pending step to focus on.

**B. Prompt Generation**
- The agent constructs a prompt using `build_action_prompt`, which includes:
  - The original user request.
  - Descriptions of available tools.
  - Recent memory context (history).
  - The current plan summary and the specific step being executed (if applicable).

**C. LLM Inference & Parsing**
- The prompt is sent to the LLM.
- The `ActionParser` attempts to parse the LLM's output into a structured `AgentAction`.
- If parsing fails, a warning is logged, and the loop continues (retrying the step).

**D. Action Handling**
Based on the parsed action type, the agent takes specific actions:

- **`finish`**: The agent concludes the task, adds a finish message to memory, and breaks the loop.
- **`ask_user`**: The agent requires user input. It logs the question and returns immediately, pausing execution.
- **`replan`**: The agent triggers a replanning event. The `Planner` updates the plan based on the current progress and reason provided. The loop then continues with the new plan.
- **`tool_call`**:
  1. **Policy Check**: The action is checked against the `PolicyChecker`. If blocked, execution is skipped. If approval is required, it is logged (auto-approved in v1).
  2. **Execution**: The `Executor` runs the tool with the provided arguments.
  3. **Memory Update**: The tool call and its result (output or error) are added to memory.
  4. **Plan Update**: If a plan is active, the status of the current step is updated to `done` or `failed`.

### 3. Conclusion Phase
After the execution loop terminates (either by finishing, hitting step limits, or completing all plan steps), the agent performs final checks and summarization.

**A. Verification**
- The agent transitions to the `verifying` state.
- It generates a `verify_prompt` containing the task and the full action history.
- The LLM is asked to verify if the task is truly complete.
- If the verification indicates missing items, a warning is logged.

**B. Summary**
- The agent generates a `summary_prompt`.
- The LLM produces a final summary of the work performed.
- The agent transitions to `completed` and returns this summary to the user.