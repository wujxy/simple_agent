# PLAN_AND_PROMPT_REFACTOR.md

## Purpose

This document is a **reference design note** for the current `simple_agent` codebase.
It is **not a strict implementation order**. The purpose is to help the implementer understand:

- what the current design problem really is,
- why the current plan logic and prompt dynamics are misaligned with agent execution,
- and what direction the next upgrade should take.

This document focuses on the following four priorities:

1. Redesign the dynamic prompt so action results become usable agent state.
2. Make `plan` an optional action rather than a hard external mode.
3. Redesign plan output so it describes **agent execution steps**, not program runtime logic.
4. Make step completion and next-action selection evidence-based.

---

## Current Diagnosis

The current system has already improved in the tool layer, but the overall loop is still not a true state-driven agent loop.

### What is good already
- The system has a clearer tool boundary than before.
- The prompt already contains anti-loop behavioral rules.
- The runtime already tracks plan progress, confirmed facts, recent observations, and working files.

### What is still broken
The main problem is no longer only “tool format”. The bigger problem is:

> The system executes actions, but the next prompt does not receive action results in a form that is rich enough to drive the next decision.

As a result:
- the agent keeps seeing pending plan items,
- but it does not truly know what the current files already contain,
- and it does not truly know whether the latest write/read/run already satisfied the next checkpoint.

That causes the common failure mode:

```text
write -> read -> still uncertain -> write again -> approval again
```

### Planning-specific diagnosis
The current `plan` output is often a decomposition of the **program's internal logic**, not the **agent's external execution logic**.

Example of a bad plan for a Gaussian fitting task:
- Generate random Gaussian data
- Create histogram of generated data
- Define Gaussian fit function
- Implement maximum likelihood fitting
- Plot histogram and fit curve
- Save plot as JPG file

This is the logic of the target Python program, not the logic of the agent.

For the agent, a better plan would be:
- inspect workspace if needed
- create or modify the source file
- run the script
- verify output artifact
- revise only if evidence shows a failure
- finish

---

## Design Goal

The target architecture should follow this principle:

> The agent should operate on explicit state transitions, not on vague summaries.

That means:
- action results must become structured prompt state,
- planning must be optional and situational,
- plan steps must describe what the agent should do,
- and completion must be determined by evidence, not by prose step labels.

---

# Priority 1 — Redesign the Dynamic Prompt Around State, Not Summaries

## Why this is first
This is the most important issue.
Even with better tools and better plans, the system will still loop if the next prompt only receives compressed summaries instead of the real action outcomes.

## Current issue
The current prompt already includes:
- confirmed facts
- working set
- recent observations
- context summary

But those are still too summary-oriented.

Typical failure:
- `read_file` succeeds,
- but the next prompt only remembers something like “file contains 57 lines”,
- not the actual file content or a useful semantic digest.

Then the model still cannot decide whether the current implementation already satisfies the remaining task.

## Upgrade direction
The dynamic prompt must be reorganized around **state projection**.

### Required dynamic blocks

#### 1. Objective block
This should explicitly state:
- user objective
- expected deliverables
- expected verification/artifact targets

Example:

```text
Objective:
- Create a runnable Gaussian fitting script.
- Produce a JPG output plot.
- Verify that the script runs successfully.
```

#### 2. Execution state block
This should state:
- whether an active plan exists
- current step ID if planned
- whether the current style is direct execution or planned execution
- whether any approval is pending

Example:

```text
Execution state:
- Active plan: yes
- Current step: S3
- Execution style: planned
- Pending approval: none
```

#### 3. Artifact snapshot block
This is the most important block.
It must carry high-value outputs forward.

Examples:
- recent `read_file` content
- recent `bash` stdout/stderr/exit code
- recent written file identity and write guarantees

Example:

```text
Artifact snapshots:
- gaussian_fit.py:
  <actual file content or structured excerpt>
- Recent shell result:
  command: python gaussian_fit.py
  exit_code: 1
  stderr: ModuleNotFoundError: ...
```

#### 4. Confirmed facts block
This should contain only narrow, tool-guaranteed facts.

Example:

```text
Confirmed facts:
- gaussian_fit.py now exactly matches the last supplied content.
- The command `python gaussian_fit.py` exited with code 1.
```

#### 5. Next decision point block
This should replace overly aggressive “next unresolved subgoal” phrasing.

Example:

```text
Next decision point:
Decide whether the current implementation already satisfies the next checkpoint,
or whether new evidence justifies another modification.
Prefer run/verify before another write unless a concrete gap is identified.
```

## Key rule
High-value payloads must survive into the next prompt.

### `read_file`
Carry forward:
- full content if small enough
- or structured excerpt if large

### `bash`
Carry forward:
- command
- exit_code
- stdout
- stderr

### `write_file`
Carry forward:
- path
- operation
- exact-match guarantee
- changed file identity

## Why this matters
Without this change, no matter how good the tool contract becomes, the model will still behave as if it is blind between turns.

---

# Priority 2 — Make `plan` an Optional Action, Not a Hard External Mode

## Why this is second
The user explicitly wants the LLM to decide whether planning is needed.
That is reasonable.
The system should not hard-code planning as a mandatory phase.

## Current issue
The system conceptually behaves too much like:

```text
enter planning mode -> generate plan -> execute
```

This is too rigid for many simple tasks.

Some tasks should skip planning entirely.
For example:
- a single-file script creation task
- a small isolated patch
- a direct write-then-run task

## Upgrade direction
Refactor the architecture into a unified loop where `plan` is just one possible action.

### Unified action loop

```text
build prompt from current state
-> model chooses one action
   - tool_call
   - plan
   - replan
   - verify
   - summarize
   - finish
-> execute action
-> update state
-> build next prompt
```

### Meaning of this design
- The runtime does **not** decide up front whether a task is “plan-mode” or “non-plan-mode”.
- The LLM chooses `plan` only when it believes a plan will improve execution.
- The runtime only stores and applies the resulting plan if one is created.

## Required prompt policy (English)

```text
Planning is optional, not mandatory.

Choose `plan` only when it will improve execution quality.
You should usually choose `plan` if:
- the task likely requires multiple files or multiple verification stages
- the current project state is unclear and must be inspected before editing
- the task has dependencies that should be sequenced carefully
- immediate action would likely cause wasteful retries

You may skip `plan` and act directly if:
- the task is small and clear
- the change likely fits in one file or a very small number of files
- you can implement first and verify with tools immediately afterward
- a plan would only restate the user's request without improving execution
```

## Expected result
This keeps planning available without forcing it onto tasks where it adds no value.

---

# Priority 3 — Redesign the Plan Schema So It Represents Agent Steps

## Why this is third
Once `plan` becomes optional, the next issue is plan quality.
The current plan style is too close to “program construction logic”.
That is not what the runtime needs.

## Current issue
Current plans often describe what the target program should do internally.
That creates artificial step granularity and causes the agent to over-edit.

The plan should instead answer:
- what files need to be inspected?
- what files need to be modified?
- what command needs to be run?
- what artifact/output needs to be verified?
- when is it safe to finish?

## Upgrade direction
Replace loose prose plans with a structured `ExecutionPlan` object.

### Suggested schema

```python
class PlanStep(BaseModel):
    step_id: str
    title: str
    purpose: str
    action_type: Literal["inspect", "read", "modify", "run", "verify", "finalize"]
    target_files: list[str] = []
    entry_conditions: list[str] = []
    completion_criteria: list[str] = []
    preferred_tools: list[str] = []


class ExecutionPlan(BaseModel):
    overview: str
    deliverables: list[str]
    likely_files: list[str]
    verification_targets: list[str]
    steps: list[PlanStep]
```

## Required plan design rules

### Rule 1 — Plans must begin with an overview
Before steps, the plan must state:
- objective
- deliverables
- likely files
- verification targets

### Rule 2 — Every step must be an agent step
Allowed step types:
- inspect
- read
- modify
- run
- verify
- finalize

Disallowed style:
- “Implement histogram logic” as a standalone execution step unless it is tied to a modify action on a file

### Rule 3 — Write-oriented steps must identify target files
A plan step that may cause a write must name the target file(s).
If target files are unknown, the correct step type is `inspect`, not `modify`.

### Rule 4 — Every step must have completion criteria
A step is not done because the tool was called.
A step is done only when evidence satisfies the step's completion criteria.

### Rule 5 — Plans must end in verification/finalization
Every coding plan must include a final verification stage.

## Example: Gaussian fit task rewritten correctly

```text
Overview:
- Deliverable: gaussian_fit.py
- Verification target: generated JPG plot

S1. Inspect workspace if needed
- action_type: inspect
- completion: know whether gaussian_fit.py already exists

S2. Create or update gaussian_fit.py
- action_type: modify
- target_files: [gaussian_fit.py]
- completion: file contains the intended implementation

S3. Run the script
- action_type: run
- target_files: [gaussian_fit.py]
- completion: script executes successfully

S4. Verify output JPG
- action_type: verify
- completion: JPG artifact exists and is produced by the script

S5. Revise only if evidence shows failure
- action_type: modify

S6. Finalize
- action_type: finalize
```

## Expected result
Plans become aligned with the actual agent loop.
They stop pushing the model into repeated writes for what should be one implementation step.

---

# Priority 4 — Make Step Completion and Next-Step Decisions Evidence-Based

## Why this is fourth
Even with a better plan schema, the system will still fail if step completion is inferred too loosely.

## Current issue
The system still behaves too much like:
- there is a pending plan item
- therefore the next action should probably move that item forward
- therefore another write is likely needed

This is not reliable.

## Upgrade direction
The runtime must evaluate completion using actual evidence from tool results.

### Evidence sources
- `write_file` success/noop with exact-match guarantee
- `read_file` content or excerpt
- `bash` execution result
- artifact existence / generated output evidence
- user clarification

## Required runtime questions after every action
After each action, the system should be able to answer:

1. What state changed?
2. Which step was this action intended to satisfy?
3. Do current facts and payloads satisfy that step's completion criteria?
4. Does the next pending step actually require a new modification?
5. Is verify/run now more appropriate than another read/write?

### Next-step hint must become conditional
Replace:

```text
Suggested next unresolved subgoal: X
```

With something like:

```text
Suggested next checkpoint:
Step S3 is still pending.
First decide whether the current state already satisfies its completion criteria.
Prefer inspect/run/verify before another write unless a specific missing requirement is identified.
```

## Required evidence-aware rules

### Rule 1 — No write without new evidence
After a successful write, another write should require one of:
- a failed verification result,
- a newly identified missing requirement,
- or a new user instruction.

### Rule 2 — No immediate read-after-write by default
After `write_file`, do not immediately read the same file again unless source-level inspection is genuinely needed.

### Rule 3 — Verification should be preferred after implementation
For code tasks, once a file has been written successfully, the system should usually prefer:
- `bash`
- `verify`

before another `write_file`.

## Expected result
Pending steps stop behaving like automatic rewrite triggers.
The agent starts behaving like a state machine driven by evidence.

---

## How the Four Priorities Work Together

These priorities are connected.

### Priority 1 enables Priority 4
Without a better dynamic prompt, there is not enough evidence in context to make evidence-based decisions.

### Priority 2 prevents over-planning
Without optional planning, simple tasks are forced into low-quality plan execution.

### Priority 3 fixes plan semantics
Without agent-step plans, even optional planning still pushes the wrong behavior.

### Priority 4 closes the loop
Without evidence-based completion, both direct execution and planned execution remain unstable.

---

## Practical Implementation Guidance

This is not a strict order, but the most natural implementation path is:

### Step A — Rebuild dynamic prompt state projection
Focus first on carrying forward:
- read file content
- shell outputs
- file write guarantees

### Step B — Remove hard conceptual dependence on “plan mode”
Refactor runtime so `plan` is just an action choice.

### Step C — Introduce structured plan objects
Do not rely only on text plans.

### Step D — Tie step completion to evidence
Make step progression conditional on actual tool results.

---

## Suggested Acceptance Criteria

The redesign is successful if the following become true:

- [ ] The model can skip `plan` for small clear tasks.
- [ ] If the model does choose `plan`, the plan describes agent steps rather than program internals.
- [ ] The next prompt can see high-value action outcomes (file content, shell outputs, file state guarantees).
- [ ] The system no longer treats a pending plan item as an automatic reason to rewrite code.
- [ ] The agent can write a file, run it, verify outputs, and finish without needing artificial intermediate source-level steps.
- [ ] For tasks like the Gaussian fit script, the agent can complete the main implementation in one write step, then use run/verify steps instead of repeatedly re-editing.

---

## Final Recommendation

Do **not** think of the next upgrade as “improve planner” alone.
The real upgrade is:

> Move from a summary-driven loop to a state-driven loop.

Planning is only one part of that.
The dynamic prompt is the real foundation, because it determines whether the model can actually see and use the results of previous actions.

If only one principle is remembered, it should be this:

> A good agent plan is a plan for what the agent should do next, not a prose decomposition of what the target program should do internally.
