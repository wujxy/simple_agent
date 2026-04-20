# Prompt 上下文优化：根治 LLM read-loop 循环

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 LLM 在工具执行成功后陷入 read-read-read 循环的问题，通过优化 prompt 结构和上下文传递，让 LLM 清晰感知已完成步骤并推进。

**Architecture:** 三层修复：(1) action prompt 增加 plan 进度总览区，展示已完成/待做步骤；(2) prompt_service 增加 completed steps 格式化；(3) resume_approval 中的 plan step 更新同时写入 session，确保重建时正确恢复。

**Tech Stack:** Python 3.10+, 现有 Pydantic/asyncio 架构

---

## File Structure

### Modified files
```
simple_agent/prompts/action_prompt.py    — 增加 plan_progress 参数，展示步骤总览
simple_agent/engine/prompt_service.py    — 增加 _format_plan_progress 方法
simple_agent/engine/query_engine.py      — resume_approval 的 plan 更新写入 session.current_plan
```

---

## Phase 1: Prompt 增加 Plan 进度总览

这是最核心的修复。当前 prompt 只告诉 LLM "current step to work on: 第一个 pending 步骤"，但完全不展示哪些步骤已完成、结果如何。LLM 无法判断"写入文件"是否已经成功，于是反复 read 验证。

### Task 1: action_prompt 增加 plan_progress 区块

**Files:**
- Modify: `simple_agent/prompts/action_prompt.py`

- [ ] **Step 1: 修改 `build_action_prompt` 函数签名和模板**

将 `simple_agent/prompts/action_prompt.py` 全文替换为：

```python
from __future__ import annotations


def build_action_prompt(
    user_request: str,
    tool_descriptions: str,
    memory_context: str,
    plan_summary: str | None = None,
    current_step: str | None = None,
    state_mode: str = "running",
    last_tool_result_str: str = "",
    plan_progress: str = "",
) -> str:
    plan_section = ""
    if plan_summary:
        plan_section = f"\nCurrent plan: {plan_summary}"
    step_section = ""
    if current_step:
        step_section = f"\nCurrent step to work on: {current_step}"
    last_result_section = ""
    if last_tool_result_str:
        last_result_section = f"\n{last_tool_result_str}\n"
    progress_section = ""
    if plan_progress:
        progress_section = f"\nPlan progress:\n{plan_progress}\n"

    return f"""You are a precise AI agent. Decide exactly one next action.

User task: {user_request}{plan_section}{step_section}

Current state: {state_mode}
{progress_section}{last_result_section}
Recent context:
{memory_context}

Available tools:
{tool_descriptions}

CRITICAL INSTRUCTIONS:
1. Respond with ONLY valid JSON
2. No explanations, no markdown, no extra text
3. Start with {{ and end with }}

Available actions:
- tool_call: Use a tool. JSON: {{"type": "tool_call", "reason": "why", "tool": "tool_name", "args": {{...}}}}
- plan: Create a plan for the task. JSON: {{"type": "plan", "reason": "why planning is needed"}}
- replan: Request a new plan. JSON: {{"type": "replan", "reason": "why the plan needs changing"}}
- verify: Check if the task is complete. JSON: {{"type": "verify", "reason": "why checking completion"}}
- summarize: Summarize progress so far. JSON: {{"type": "summarize", "reason": "why summarizing"}}
- ask_user: Ask for clarification. JSON: {{"type": "ask_user", "reason": "why", "message": "your question"}}
- finish: Task is complete. JSON: {{"type": "finish", "reason": "why done", "message": "summary of what was accomplished"}}

Rules:
- Choose exactly ONE action
- Use tools when you need information or to perform actions
- Use plan for complex tasks that need decomposition
- Use verify when you think the task might be done
- Use summarize to consolidate progress on long tasks
- Finish only when the task is fully complete
- Ask the user if you are stuck or need clarification
- Do NOT repeat a tool call that already succeeded (check Plan progress above)

Response (JSON only):"""
```

关键变化：
1. 新增 `plan_progress: str = ""` 参数
2. 新增 `progress_section` 变量，当 plan_progress 非空时展示
3. 在 Rules 末尾增加 "Do NOT repeat a tool call that already succeeded" 提示
4. progress_section 放在 last_result_section 之前，让 LLM 先看到进度全景

- [ ] **Step 2: 验证语法**

Run: `cd /home/NagaiYoru/Agents/my_agent/simple_agent && python -c "from simple_agent.prompts.action_prompt import build_action_prompt; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add simple_agent/prompts/action_prompt.py
git commit -m "feat: add plan_progress and anti-repeat rule to action prompt"
```

---

### Task 2: prompt_service 增加 plan 进度格式化

**Files:**
- Modify: `simple_agent/engine/prompt_service.py`

- [ ] **Step 1: 添加 `_format_plan_progress` 方法并传入 `build_action_prompt`**

在 `simple_agent/engine/prompt_service.py` 中：

(a) 在 `build_action_prompt` 方法中，在 `last_result_str = ...` 行之后添加：

```python
        plan_progress = self._format_plan_progress(state.current_plan)
```

(b) 在 `return build_action_prompt(...)` 调用中添加 `plan_progress=plan_progress` 参数：

```python
        return build_action_prompt(
            user_request=state.user_message,
            tool_descriptions=tool_descriptions,
            memory_context=memory_context,
            plan_summary=plan_summary,
            current_step=current_step,
            state_mode=state.mode,
            last_tool_result_str=last_result_str,
            plan_progress=plan_progress,
        )
```

(c) 在 `_format_last_tool_result` 方法之后添加新方法：

```python
    def _format_plan_progress(self, plan: dict | None) -> str:
        if not plan or not plan.get("steps"):
            return ""
        lines: list[str] = []
        for i, step in enumerate(plan["steps"], 1):
            status = step.get("status", "pending")
            title = step.get("title", f"Step {i}")
            if status == "done":
                notes = step.get("notes", "")
                note_str = f" -> {notes[:100]}" if notes else ""
                lines.append(f"  [done] {title}{note_str}")
            elif status == "failed":
                lines.append(f"  [failed] {title}")
            else:
                lines.append(f"  [pending] {title}")
        return "\n".join(lines)
```

这个方法把 plan 的每个步骤格式化为 `[done]` / `[failed]` / `[pending]` 的清单。对于已完成的步骤还会附加 notes（截断到 100 字符），这样 LLM 能直接看到 "write_file -> Successfully wrote to 'xxx'" 而不需要去 memory 碎片中翻找。

- [ ] **Step 2: 验证语法**

Run: `cd /home/NagaiYoru/Agents/my_agent/simple_agent && python -c "from simple_agent.engine.prompt_service import PromptService; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add simple_agent/engine/prompt_service.py
git commit -m "feat: prompt_service formats plan progress for LLM context"
```

---

## Phase 2: Plan 进度持久化修复

当前 `resume_approval` 更新 plan step status 时，修改的是 `state.current_plan`（从 `rebuild_state_from_turn` 恢复的 dict），但 `rebuild_state_from_turn` 中 `state.current_plan = session.current_plan` 是**引用赋值**（Python dict 是可变对象），所以修改 `state.current_plan` 也会修改 `session.current_plan`。

但问题在于 `rebuild_state_from_turn` (transitions.py:104-105) 的代码是：
```python
if session and session.current_plan:
    state.current_plan = session.current_plan
```
这是引用赋值，所以 `resume_approval` 中对 `state.current_plan` 的修改确实会反映到 `session.current_plan`。后面也调用了 `self._session_store.save_session(session)` (query_engine.py:178)，所以 session 被保存了。

然而，这个引用关系在 `apply_transition` 中会被打破：`dataclasses.replace(state)` 是浅拷贝，`current_plan` 字段仍然是同一个 dict 引用。所以理论上没问题。

**但是**，`submit_message` 中的初始化 (query_engine.py:78-84) 使用 `current_plan=session.current_plan`，如果 session 已有 plan，这是正确的引用。`resume_user_input` 通过 `rebuild_state_from_turn` 也用引用。所以 plan 进度在正常流程中是正确的。

**真正的问题**：在 `dispatcher._handle_tool_call` (dispatcher.py:79-85) 中，plan step 更新后调用了 `deps.session_store.save_session(deps.session)`。但 `deps.session` 来自 `QueryParam.session`，这是 `_build_deps` 中传入的同一个对象。所以 session 被保存了。

综合分析：plan 进度的引用链在大多数路径上是正确的，但 `resume_approval` 中的 plan 更新已经通过 `self._session_store.save_session(session)` 保存。这个阶段不需要额外代码修改。

### Task 3: 验证 plan 进度传递链完整性（只读验证，不改代码）

- [ ] **Step 1: 追踪验证**

在以下三个路径中，确认 `session.current_plan` 的一致性：

1. `submit_message` → `query_loop` → `dispatcher._handle_tool_call` → plan step 更新 → `save_session`
2. `resume_approval` → plan step 更新 → `save_session` → `query_loop` → `dispatcher._handle_tool_call` → plan step 更新 → `save_session`
3. `rebuild_state_from_turn` → `state.current_plan = session.current_plan`（引用） → 修改 state.current_plan 即修改 session.current_plan

如果以上链路确认无问题（引用一致性），则此 Task 标记完成。如果发现断裂点，需补充 `session.current_plan = state.current_plan` 的显式回写。

- [ ] **Step 2: 如果发现问题则修复**

如果在 Step 1 中发现 `session.current_plan` 未被正确更新，在 `query_engine.py` 的 `resume_approval` 方法中，将 plan 更新后的保存改为：

```python
            if state.current_plan:
                for step in state.current_plan.get("steps", []):
                    if step.get("status") == "pending":
                        step["status"] = "done" if result.success else "failed"
                        step["notes"] = result_str[:200]
                        break
                session.current_plan = state.current_plan
                self._session_store.save_session(session)
```

（仅当 Step 1 确认需要时才执行此修改）

- [ ] **Step 3: Commit (if changed)**

```bash
git add simple_agent/engine/query_engine.py
git commit -m "fix: ensure session.current_plan synced after approval plan update"
```

---

## Phase 3: 端到端验证

### Task 4: 手动端到端测试

- [ ] **Step 1: 启动 app 并执行 write_file 任务**

```bash
cd /home/NagaiYoru/Agents/my_agent/simple_agent
ZHIPU_API_KEY=<your_key> python -m simple_agent.app
```

测试场景：
1. 提交需要 write_file 的任务（如 "write 'hello world' to /tmp/test.txt"）
2. 确认出现审批提示
3. 输入 `y` 批准
4. **核心验证点**：确认 LLM 不再反复 read 同一文件
5. 确认 LLM 推进到 verify 或 finish

- [ ] **Step 2: 测试复杂多步骤任务**

提交需要多步的任务（如之前的高斯拟合任务）：
1. 确认 plan 进度在 prompt 中正确展示
2. 确认每步完成后 LLM 推进到下一步
3. 确认不存在重复 read 循环

---

## Verification Checklist

- [ ] `python -c "from simple_agent.prompts.action_prompt import build_action_prompt; print('OK')"` — 语法正确
- [ ] `python -c "from simple_agent.engine.prompt_service import PromptService; print('OK')"` — 语法正确
- [ ] 手动测试：write_file 审批后 LLM 推进到下一步，不循环 read
- [ ] 手动测试：多步骤任务中 plan progress 正确展示 done/pending 状态
