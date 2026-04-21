# PROMPT_MINIMAL_REFACTOR_PLAN.md

# simple_agent Prompt 最小化重构方案

> 目标：不新增新的上下文层级系统，不大改架构，只通过：
>
> 1. **优化 tool result 的表达方式**
> 2. **优化 prompt 中的状态/进展/规则表达**
> 3. **减少重复注入和原始日志堆积**
>
> 来解决当前常见问题：
>
> - 模型无法确认 `write_file` / `bash` 已经执行完成
> - 模型在写入后仍反复读取或再次申请写入
> - prompt 中同类信息重复过多，事实不够硬，完成证据不明确
>
> 本方案面向执行者（如 Claude Code / GLM），要求以最小修改代价提升 prompt 质量，不引入新的复杂上下文层。

---

# 1. 当前问题总结

## 1.1 问题一：tool result 更像日志，不像事实
当前 prompt 中，`write_file` 和 `bash` 的结果更多是：
- diff 片段
- stdout/stderr 片段
- 截断后的文本

这会让模型把它们理解成“线索”，而不是“已经发生的事实”。

### 后果
- `write_file` 成功后模型仍想再读回确认
- `bash` 成功后模型仍想再次运行确认
- 模型反复申请写入 / 审批

---

## 1.2 问题二：prompt 重复注入同类信息
当前同一个工具结果可能出现在：
- plan progress
- recent observations
- context summary
- working set

### 后果
- token 浪费
- 强化“我刚做过动作”，却没有强化“这个动作已经完成了哪些语义目标”
- 模型更容易进入循环式确认

---

## 1.3 问题三：Current step 过强，像硬命令
当前 prompt 中：

```text
Current step: Create histogram of generated data
```

这类表述会强烈推动模型“继续写代码推进当前步骤”，即使已有代码可能已经完成了这一步。

### 后果
- 模型被迫继续写
- 缺少“先判断是否已完成”的空间
- 容易触发重复写入和再次审批

---

## 1.4 问题四：没有显式的“已确认事实”区块
当前 prompt 中虽然有 tool result，但缺少统一的：

> Confirmed facts

即：把最近的工具结果整理成“模型可以直接信任的结论”。

### 后果
- 模型要自己从原始日志推导
- 认知负担高
- 容易保守地再次读取/写入/运行

---

# 2. 本次重构的目标

本次重构只做三件事：

## 2.1 把工具结果改写为“事实型表达”
特别是：
- `write_file`
- `bash`

不再重点返回原始 diff / 原始输出，而是返回：
- 是否成功
- 影响对象
- 可被信赖的事实结论
- 必要的简短元信息

---

## 2.2 在 prompt 中增加统一的 `Confirmed facts` 区块
将最近的关键工具结果转换成高密度事实摘要。

---

## 2.3 调整行为规则与当前步骤表述
核心思想：
- 不再把“当前 step”写成强命令
- 不再把“不要重读”写成死规则
- 而是写成更工程化、更可执行的判断规则

---

# 3. 设计原则

## 3.1 模型应把成功工具结果当作事实
一旦工具成功，其结果应该具有“承诺语义”。

例如：
- `write_file` 成功 -> 文件现在就是你写进去的内容
- `bash` 成功 -> 命令已经执行完，退出码和 artifact 可作为事实依据

---

## 3.2 工具结果不应重复回放原始大段内容
对模型自己生成并提交的内容（如 `write_file.content`），不要再通过 prompt 把大段 diff/全文反复喂回去。

---

## 3.3 一个事实只注入一次
最近的关键结果统一进入 `Confirmed facts`，不要在多个区块重复。

---

## 3.4 prompt 只表达当前必要事实
prompt 不是运行日志回放器，而是决策控制面。

---

# 4. 工具结果表达协议重构

## 4.1 `write_file` 的新结果表达

### 当前问题
当前结果更像：
- `created, +78/-0 lines`
- diff 片段
- 截断 patch

### 新协议
`write_file` 成功时返回结构化事实摘要：

```python
{
    "ok": True,
    "tool": "write_file",
    "path": "gaussian_fit.py",
    "created": True,
    "overwritten": False,
    "lines_written": 78,
    "bytes_written": 2431,
    "content_fingerprint": "sha1:abcd1234",
    "model_already_knows_content": True,
    "summary": "gaussian_fit.py was created successfully. The file now matches the content supplied in this call."
}
```

### Prompt 中展示格式
```text
write_file(gaussian_fit.py) -> SUCCESS
Fact: gaussian_fit.py now exactly matches the content you supplied in that call.
Created: yes
Lines written: 78
Fingerprint: sha1:abcd1234
```

### 特别规则
默认不展示：
- 全量 diff
- 全量 patch
- 全量写入内容

仅在以下场景展示 patch/diff：
- edit/patch 型工具
- 写入被截断
- 写入部分失败
- 用户明确要求看 diff

---

## 4.2 `bash` 的新结果表达

### 当前问题
bash 容易只返回一大段 stdout/stderr。

### 新协议
`bash` 成功时返回：

```python
{
    "ok": True,
    "tool": "bash",
    "command": "python gaussian_fit.py",
    "exit_code": 0,
    "stdout_summary": "Script ran successfully and produced gaussian_fit.jpg.",
    "stderr_summary": "",
    "artifacts": ["gaussian_fit.jpg"],
    "summary": "Command completed successfully. The JPG output file was created."
}
```

### Prompt 中展示格式
```text
bash("python gaussian_fit.py") -> SUCCESS
Exit code: 0
Artifacts created: gaussian_fit.jpg
Fact: the script completed successfully.
```

### 特别规则
默认不展示：
- 全量 stdout
- 全量 stderr

仅展示：
- 退出码
- 关键信息摘要
- artifact
- 必要错误摘要

---

## 4.3 `read_file` 的新结果表达

### 当前问题
read_file 的结果常被重复注入全文或片段。

### 新协议
返回：

```python
{
    "ok": True,
    "tool": "read_file",
    "path": "gaussian_fit.py",
    "lines": 78,
    "summary": "The file contains Gaussian data generation, histogram plotting, MLE fitting, and JPG saving logic.",
    "content": "..."
}
```

### Prompt 中展示格式
优先给 summary，必要时保留全文或截断内容：

```text
read_file(gaussian_fit.py) -> SUCCESS
Summary: The file contains Gaussian data generation, histogram plotting, MLE fitting, and JPG saving logic.
```

### 特别规则
- 最近连续重复的 `read_file` 不重复注入全文
- 如果同一个文件未变化，则优先复用 summary

---

## 4.4 通用 ToolResult 格式建议

建议统一：

```python
from dataclasses import dataclass

@dataclass
class ToolResult:
    success: bool
    tool_name: str
    args: dict
    summary: str
    facts: list[str]
    output: str | None = None
    metadata: dict | None = None
```

### 说明
- `summary`：人类可读简短结论
- `facts`：给 prompt 用的“硬事实”
- `output`：仅在必要时保留原始输出
- `metadata`：结构化补充信息

---

# 5. Prompt 构建逻辑最小重构

## 5.1 目标
不引入新层，只重组已有信息，统一表达成更可消费的 prompt。

---

## 5.2 Prompt 最小结构

建议当前 action prompt 重构为以下顺序：

```text
[System core]
[Available tools and actions]
[Current state]
[Plan status]
[Confirmed facts]
[Working set]
[Recent observations (minimal)]
[User task]
[Suggested next unresolved subgoal]
[Response format]
```

---

## 5.3 为什么这样排

### System core 在前
保持稳定。

### Tools/actions 在前
让模型一开始就知道动作空间。

### Current state + Plan status 在中间
告诉模型当前处于什么运行态。

### Confirmed facts 在 Plan 之后
这是最关键的：让模型先知道最近已经“确定完成了什么”。

### Working set + recent observations 在 facts 之后
作为辅助，而不是主信息。

### User task + current subgoal 在后
作为当前驱动输入。

---

# 6. `Confirmed facts` 区块模板（必须新增）

## 6.1 目标
把最近关键工具结果统一转成模型可直接信赖的事实。

## 6.2 模板

```text
Confirmed facts:
- write_file(gaussian_fit.py) succeeded.
  Fact: gaussian_fit.py now exactly matches the content supplied in that call.
- read_file(gaussian_fit.py) succeeded.
  Fact: the file currently contains Gaussian data generation, histogram plotting, MLE fitting, and JPG saving logic.
- bash("python gaussian_fit.py") succeeded.
  Fact: gaussian_fit.jpg was created successfully.
```

## 6.3 规则
- 只保留最近关键 1~3 条
- 同一事实不在 Plan progress / Context summary 重复出现
- 不放 raw diff / raw stdout

---

# 7. 行为规则最小重写

## 7.1 当前规则问题
当前类似：
- “After writing a file, do NOT re-read it”
这种规则过于死板，且和“继续推进任务”容易冲突。

## 7.2 替换后的规则模板

建议替换为：

```text
Behavioral rules:
1. Respond with ONLY valid JSON — no explanations, no markdown, no extra text.
2. Choose the single best next action for this turn.
3. Treat successful tool results as facts.
4. If write_file succeeds, assume the file now matches the content you supplied unless the tool reports otherwise.
5. Do not re-read a file you just wrote unless you need a specific verification that is not already available from the write result or file summary.
6. Before requesting another write, check whether the current file already satisfies the remaining subgoals.
7. Prefer verify, summarize, or finish over repeated writes when the current code likely already covers the requirements.
8. Do not repeat an identical successful tool call without a new reason.
9. Ask the user only if you are blocked by missing information or an approval decision.
```

### 为什么这样更好
因为它不是禁止模型行动，而是给模型提供明确判断准则。

---

# 8. `Current step` 表达方式重构

## 8.1 当前问题
当前写法：

```text
Current step: Create histogram of generated data
```

太像“强命令”，会直接推动模型继续写。

## 8.2 替换模板

改为：

```text
Suggested next unresolved subgoal:
Create histogram of generated data, only if this is not already implemented in the current file.
```

或者：

```text
Next unresolved subgoal (if still missing):
Create histogram of generated data.
```

### 为什么这样改
这样模型会先结合 `Confirmed facts` 判断当前代码是否已经覆盖该需求。

---

# 9. `Plan progress` 区块重构

## 9.1 当前问题
Plan progress 里不应塞 raw diff 或原始 tool 结果片段。

## 9.2 新模板

```text
Plan progress:
- [done] Generate random Gaussian numbers
- [done] Create histogram of generated data
- [done] Define Gaussian fit function
- [pending] Implement maximum likelihood fitting
- [pending] Create visualization
- [pending] Save plot as JPG
```

可选附加：

```text
Reasoning note:
Current file likely already covers steps 1-3 based on the latest confirmed facts.
```

### 关键规则
Plan progress 只放：
- done / pending
- 简短原因
- 不放 patch / diff / raw output

---

# 10. `Recent observations` 区块重构

## 10.1 当前问题
Recent observations 容易和 Confirmed facts 重复。

## 10.2 新模板
只保留无法完全固化为 fact 的最近观察：

```text
Recent observations:
- No execution has yet confirmed that gaussian_fit.jpg is produced.
- The latest write created gaussian_fit.py successfully.
```

### 原则
- facts 放 facts
- observation 放不确定但相关的信息
- 不重复

---

# 11. 推荐 Prompt 模板（可直接使用）

下面给出一份可直接替换当前 action prompt 的模板。

## 11.1 推荐模板

```text
You are a precise AI agent that executes tasks step by step.

Behavioral rules:
1. Respond with ONLY valid JSON — no explanations, no markdown, no extra text.
2. Choose the single best next action for this turn.
3. Treat successful tool results as facts.
4. If write_file succeeds, assume the file now matches the content you supplied unless the tool reports otherwise.
5. Do not re-read a file you just wrote unless you need a specific verification that is not already available from the write result or file summary.
6. Before requesting another write, check whether the current file already satisfies the remaining subgoals.
7. Prefer verify, summarize, or finish over repeated writes when the current code likely already covers the requirements.
8. Do not repeat an identical successful tool call without a new reason.
9. Ask the user only if you are blocked by missing information or an approval decision.

Available tools:
{tool_list}

Available actions:
{action_list}

Current state:
mode={mode}
step={step_count}/{max_steps}
plan_progress={done_steps}/{total_steps}
last_tool={last_tool_summary}

Plan progress:
{plan_progress_lines}

Confirmed facts:
{confirmed_facts_lines}

Working set:
{working_set_lines}

Recent observations:
{recent_observation_lines}

User task:
{user_task}

Current plan:
{current_plan_summary}

Suggested next unresolved subgoal:
{next_subgoal_if_still_missing}

Response (JSON only):
```

---

# 12. 代码修改点（最小）

## 12.1 修改 `tools/tool_executor.py`
目标：
- 让 `write_file` / `bash` / `read_file` 返回结构化 summary + facts
- 不再默认返回大段 diff / stdout

---

## 12.2 修改 `context/context_service.py`
目标：
- 新增 `confirmed_facts`
- 从 recent tool results 中提炼事实
- 去重
- 不再把同类信息重复注入多个区块

---

## 12.3 修改 `prompts/action_prompt.py`
目标：
- 替换行为规则
- 新增 `Confirmed facts`
- 弱化 `Current step`，改为 `Suggested next unresolved subgoal`

---

## 12.4 修改 `engine/prompt_service.py`
目标：
- 调整 prompt 各区块顺序
- 去掉重复 tool result 注入
- 只保留最关键 observation

---

# 13. 实施顺序

## Step 1
先改 `write_file` / `bash` / `read_file` 的结果表达协议。

## Step 2
在 ContextService 中抽取 `confirmed_facts`。

## Step 3
重写 action prompt 模板。

## Step 4
去掉 Plan progress / Context summary / Recent observations 中的重复原始内容。

---

# 14. 验收标准

完成后，系统应满足：

- `write_file` 成功后，模型能将其视为“文件已写入完成的事实”
- `bash` 成功后，模型能将退出码和 artifact 视为完成依据
- prompt 中不再重复出现大段 diff / stdout / file content
- `Current step` 不再强迫模型继续写
- 同一文件写入后，模型显著减少为了确认而再次 read 的行为
- 重复写入/审批循环显著减少

---

# 15. 一句话总结

本次最小重构的核心不是“加新层”，而是：

> **把工具结果从“日志片段”重构为“可被模型直接信赖的事实表达”，并围绕这些事实重组 prompt。**

执行者必须优先优化：
- `write_file` / `bash` 的事实型返回
- `Confirmed facts` 区块
- `Current step` 的表达方式
而不是继续堆叠新的上下文层。
