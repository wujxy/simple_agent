# PLAN_AND_PROMPT_REFACTOR_V2.md

## Purpose

This document is a **risk-focused refinement** of the previous prompt-and-plan refactor proposal.

The previous plan was directionally strong, but several items would likely introduce new failure modes if implemented literally.

This v2 document does **not** replace the whole strategy. Instead, it clarifies:
- which parts of the original proposal are sound,
- which parts are risky,
- what should be changed before implementation,
- and how to keep the redesign aligned with a real state-driven agent loop.

---

## Summary Judgment

The original four-priority direction remains valid:

1. Rebuild the dynamic prompt around state projection.
2. Make `plan` an optional action rather than a hard external mode.
3. Redesign plans as agent execution steps.
4. Make step completion evidence-based.

However, the previous version is **unsafe to execute literally** in several places.

The main risks are:
- prompt over-expansion,
- text projection without true underlying state structure,
- dangerous fallback behavior for invalid plans,
- over-greedy step completion logic,
- and force-advance mechanisms that hide design mistakes instead of fixing them.

---

# Risk 1 — Prompt Payload Explosion

## Original risk
The previous proposal increased:
- file snapshot size,
- shell result window size,
- stdout/stderr size,
- artifact summary density,
- and contextual blocks.

This is directionally correct, but if implemented literally it can create a new problem:

> The prompt becomes much richer, but also much heavier, noisier, and more unstable.

That can lead to:
- worse JSON output stability,
- more parse failures,
- important evidence being drowned in low-priority payloads,
- and weaker next-action reasoning despite more context.

## Correction
Add a **Prompt Budget & Selection Policy**.

### Required design rule
Do not inject all available high-value payloads.
Inject only the payloads most relevant to the next decision.

### Recommended policy
- keep at most **1–2 file snapshots** per turn
- keep at most **1 most relevant shell result** per turn
- prefer snapshots relevant to the active step or current decision point
- keep only the **latest snapshot per path**
- invalidate stale snapshots after later writes
- prefer structured excerpts over large raw dumps unless the file is small

### Recommendation
Phase 1 must explicitly include:

```text
Prompt budget policy:
- Do not maximize payload volume.
- Maximize decision-relevant evidence under a bounded token budget.
```

---

# Risk 2 — Bigger Prompt Blocks Without a True Artifact State Model

## Original risk
The previous proposal focused heavily on prompt blocks such as:
- artifact snapshots
- shell result blocks
- objective block
- next decision point block

That is useful, but if implemented only as “more text assembly”, the design will remain summary-driven.

This would create the illusion of statefulness while still relying on text concatenation.

## Correction
Introduce a **structured artifact state layer** first, then render it into prompt text.

### Required internal state model
The runtime should maintain something like:

```python
class ArtifactState(BaseModel):
    files: dict[str, dict] = {}
    shell_results: list[dict] = []
    outputs: dict[str, dict] = {}
```

Example stored file state:

```json
{
  "gaussian_fit.py": {
    "exists": true,
    "snapshot": "...",
    "last_write_exact_match": true,
    "last_updated_turn": 4
  }
}
```

### Required projection rule
Prompt blocks should be projections of structured state, not the primary storage location of state.

### Recommendation
Phase 1 should be reframed as:
- first strengthen artifact state in memory/runtime,
- then redesign prompt blocks to project selected parts of that state.

---

# Risk 3 — Wrong Acceptance Criterion for Optional Planning

## Original risk
The previous plan included validation language similar to:

> simple tasks do not trigger `plan`

That is too strict under the desired design philosophy.

The user explicitly wants:
- planning not to be hard-coded,
- and the LLM to decide whether planning is useful.

If that is true, then “simple tasks never trigger plan” is not a valid acceptance criterion.

## Correction
The acceptance criterion must target **runtime behavior**, not exact LLM behavior.

### Replace this kind of criterion
```text
Simple tasks do not trigger plan.
```

### With this
```text
The runtime does not force planning before execution.
The prompt encourages direct execution for simple clear tasks.
The LLM is allowed to skip planning when planning would not improve execution.
```

### Recommended principle
Judge the redesign by whether the system **permits correct direct execution**, not by whether the model always chooses it.

---

# Risk 4 — Dangerous Fallback: Invalid Plan -> Finalize Step

## Original risk
The previous proposal suggested that if plan parsing fails, the planner may fall back to a one-step plan with `action_type="finalize"`.

This is dangerous.

If planning fails, it means:
- the planner output was malformed,
- the prompt/schema was not followed,
- or the task was not successfully converted into a structured plan.

That is **not** a reason to move toward finalization.

## Failure mode
This can bias the system toward:
- summarize,
- finish,
- or otherwise under-planned execution

even though the real problem is schema failure, not task completion.

## Correction
Use one of the following safer fallbacks instead.

### Safe Fallback A — No plan
Return `None` and continue in direct execution mode.

### Safe Fallback B — Inspection plan
Return a minimal conservative plan:

```json
{
  "overview": "Planner failed to produce a structured plan; fall back to inspection.",
  "steps": [
    {
      "step_id": "S1",
      "action_type": "inspect",
      "title": "Inspect current project state",
      "completion_criteria": ["Relevant files and current state are identified."]
    }
  ]
}
```

### Hard rule
Never fall back to `finalize` just because structured planning failed.

---

# Risk 5 — Step Completion Is Still Too Greedy

## Original risk
The previous version improved step completion logic, but still proposed mappings like:
- `modify` -> `write_file success` -> `done`
- `run` -> `bash exit 0` -> `done`
- `read` -> `read success` -> `done`

This is still too aggressive.

## Why this is dangerous
A successful tool call does not always satisfy the semantic goal of the step.

Example:
- a `write_file` call proves that the file now matches the supplied content,
- but it does **not automatically prove** that the intended functionality is correct or complete.

## Correction
Introduce **two layers of step completion**.

### 1. Structural completion
The step's immediate operation succeeded.
Examples:
- file was written,
- command ran,
- file content was read.

### 2. Semantic completion
The step's actual completion criteria are satisfied.
Examples:
- the file now contains the required implementation,
- the script runs correctly,
- the artifact exists,
- verification targets passed.

### Recommended runtime states
For a step, use at least one intermediate notion such as:
- `pending`
- `candidate_done`
- `done`
- `failed`
- `blocked`

### Example
For a `modify` step:
- `write_file success` -> `candidate_done`
- then prefer `run`/`verify`
- only mark `done` when evidence supports completion

### Recommendation
Do **not** directly map `modify -> write success -> done` in the generic case.

---

# Risk 6 — Force-Advance After N Successes Hides Design Bugs

## Original risk
The previous version suggested a safety valve such as:
- if three successful tools do not advance the step,
- force-advance with a warning.

This is risky.

## Why this is dangerous
If step completion logic is weak, force-advance will:
- hide the weakness,
- advance the wrong step,
- propagate invalid state downstream,
- and make later failure analysis harder.

## Correction
Replace force-advance with one of these outcomes:

### Option A — Mark blocked
```text
The current step has not reached completion despite multiple successful actions.
Mark it as blocked and surface that state in the prompt.
```

### Option B — Suggest replan
```text
The current step definition may be too coarse or misaligned with available evidence.
Consider replanning.
```

### Option C — Emit diagnostic warning only
Keep the step pending, but surface a warning in the next decision point block.

### Hard rule
Do not auto-advance a step merely because multiple successful tool calls occurred.

---

# Risk 7 — “New Evidence” Definition Is Too Loose

## Original risk
The previous proposal implied that even a successful `bash` run might count as justification for another write.

This is too permissive.

## Why this is dangerous
If `bash exit 0` is treated as generic evidence for more editing, the agent may keep modifying already-working implementations.

## Correction
Strengthen the definition of “new evidence” for allowing another write.

### Strong write-enabling evidence
- failed `bash` result
- failed/incomplete verification
- new user requirement
- `read_file` reveals a concrete missing implementation detail

### Usually NOT sufficient alone
- `bash exit 0`
- generic pending plan text
- the fact that the task is not yet summarized

### Recommended rule
After a successful write, prefer:
- `run`
- `verify`
- `finish`

over another write, unless there is concrete evidence of a problem or gap.

---

# Risk 8 — Plan Steps Need Clear Semantics for `inspect` vs `read`

## Original risk
The previous schema introduced both:
- `inspect`
- `read`

but did not clearly define the distinction.

This ambiguity could cause inconsistent planning and completion logic.

## Correction
Define them explicitly.

### Recommended distinction
- `inspect`: discover project/workspace state, file existence, or candidate targets
- `read`: retrieve known file content for reasoning

### Example
- `list_dir`, checking existence, or selecting files -> `inspect`
- reading `gaussian_fit.py` content -> `read`

### Recommendation
Document this distinction in the planner prompt and runtime logic.

---

# Risk 9 — Objective Inference Without Explicit Assumption Tracking

## Original risk
The previous proposal suggested generating an objective block from the user message when no plan exists.

That is useful, but if done carelessly it can cause the system to invent deliverables or verification goals not explicitly grounded in user intent.

## Correction
Split objective representation into two parts.

### 1. User objective
A normalized restatement of what the user asked.

### 2. Working assumptions
Any inferred deliverables or verification targets should be marked explicitly as assumptions.

### Example
```text
User objective:
- Create a Gaussian fitting program and save a JPG plot.

Working assumptions:
- The output JPG should be generated by running the script.
- The main source file will likely be gaussian_fit.py.
```

This reduces silent hallucinated planning constraints.

---

# Revised Guidance for the Four Priorities

## Priority 1 — Keep it, but add budget + state-model discipline
Keep the direction, but add:
- prompt budget policy
- artifact-state-first architecture
- freshness/invalidation rules

## Priority 2 — Keep it, but soften acceptance expectations
Keep optional planning, but do not require that the model never plans for simple tasks.
Validate that the runtime no longer forces planning.

## Priority 3 — Keep it, but fix failure fallback and semantic precision
Keep `ExecutionPlan`, but:
- remove finalize fallback
- define `inspect` vs `read`
- require plans to remain conservative when uncertain

## Priority 4 — Keep it, but avoid greedy completion and force-advance
Keep evidence-based step logic, but:
- distinguish structural vs semantic completion
- use `candidate_done` / `blocked` / `needs_verify`
- never force-advance because of repeated successful calls alone

---

## Practical Recommendation for the Implementer

If this refactor is executed, it should be interpreted in this order of concern:

1. **Do not let Phase 1 become uncontrolled prompt inflation.**
2. **Do not let Phase 3 fallback accidentally bias the agent toward finish/finalize.**
3. **Do not let Phase 4 completion logic reintroduce hidden greedy step advancement.**
4. **Do not mistake better prompt text for a complete state model.**

The redesign will only work if the system becomes more state-driven at runtime, not merely more verbose in prompt construction.

---

## Final Recommendation

The previous plan should still be used as the main directional backbone, but it should be patched with the risk corrections in this v2 document before implementation.

If only one core correction is remembered, it should be this:

> Do not transform the old summary-driven system into a larger summary-driven system.
> The redesign must strengthen underlying state representation, then project only the most decision-relevant parts into prompt text.
