# NEXT_STAGE_UPGRADE_PLAN.md

# simple_agent 下一阶段升级计划

> 目标：在当前 `SessionRuntime + QueryKernel + Hook-Based Approval` 架构基础上，集中推进以下三条主线：
>
> 1. **Memory / Turn Context 管理升级**：分层上下文、working set、compact、摘要压缩
> 2. **工具 Batch 化与并行调度**：先做只读工具的批量并行，后续再扩展到多文件写入
> 3. **Prompt 构建体系优化**：借鉴 Claude Code 的五层 Prompt Builder 设计，构建更稳定、更经济、更适配状态机内核的 prompt 体系
>
> 本文档面向执行者（如 Claude Code / GLM），要求按模块理解、按阶段实施，不要将三条主线割裂实现。

---

# 1. 当前架构状态

当前 `simple_agent` 已完成：

- 程序常驻（SessionRuntime）
- QueryEngine / query_loop 分层
- QueryState + Transition 状态机方向
- ToolExecutor 独立
- Hook-Based 审批链路
- 基础 PromptService / ContextService / MemoryService

但当前系统仍存在三类核心短板：

## 1.1 上下文管理仍然过于简单
目前 session memory 与 turn context 主要还是：
- recent history
- recent memory
- current plan
- last tool result

本质上仍然偏向“最近窗口 + 直接截断”的简单上下文管理。

### 后果
- prompt 膨胀
- 历史噪声累积
- 重复读文件结果堆积
- 已完成动作难以压缩
- working set 不清晰

---

## 1.2 工具执行仍是单 action、单工具、串行推进
当前 query kernel 本质上仍是：

```text
一轮 LLM -> 一个 action -> 一个 tool -> 等结果 -> 下一轮
```

这意味着：
- LLM 一次只能发一个工具
- 多个文件读取不能并行
- 不能在“部分任务已完成”时继续调度其它任务
- scheduler 层尚未出现

---

## 1.3 Prompt 构建仍然偏单层
当前 prompt 虽然已经优于早期版本，但整体仍更像：
- 系统说明
- 当前任务
- 当前状态
- 最近上下文
- 工具列表
- 输出 schema

缺少 Claude Code 那种：
- 分层拼接
- 动态注入
- 规则层
- working set 层
- batch 协议层
- 缓存友好型结构

---

# 2. 下一阶段的总体设计原则

## 2.1 不再把 Prompt 当成一个字符串，而是一个构建流水线
Prompt 的职责不是“告诉模型所有事情”，而是：
- 以最小必要信息表达当前工作状态
- 给模型一个受控的动作空间
- 强化 progress 与 working set
- 支持 batch 工具调度

---

## 2.2 不再把 Context 当成 recent history，而是一个多层工作记忆系统
Context 必须明确区分：
- 原始会话日志
- 当前 query 状态投影
- 文件工作集
- compact summary
- 最新动态观察

---

## 2.3 并行化不是“同时发多个 await”，而是引入任务调度层
要支持 batch tools / 并行执行，必须引入：
- TaskSpec
- in-flight task state
- scheduler
- batch action schema
- conflict analysis

---

## 2.4 三条主线必须联动
- Context 不升级，Prompt 无法真正优化
- Prompt 不升级，Batch Tool 协议无法稳定引导模型
- Scheduler 不升级，状态机仍然只能 step-by-step

因此三条主线要协同推进，而不是分别孤立实现。

---

# 3. 主线一：Memory / Turn Context 管理升级

## 3.1 升级目标

把当前的“最近窗口 + 轻量裁剪”升级为真正的**分层上下文管理系统**。

### 核心目标
- 建立分层 context
- 维护 working set
- 支持 compact / summary
- 减少无效工具输出堆积
- 提高模型对当前任务真实进展的感知

---

## 3.2 目标结构：五层上下文

建议将上下文拆成以下五层。

### Layer A：Session Raw Log（原始日志层）
保存完整 session history，不直接全量进入 prompt。

内容包括：
- 用户消息
- assistant 消息
- tool 调用
- tool 结果
- approval 事件
- verify 事件

### Layer B：QueryState Projection（当前状态层）
由 QueryState 投影得到：

- mode
- current_plan
- step_count / max_steps
- last_tool_result 摘要
- last_verify_result 摘要
- transition_reason
- pending_action 摘要

这是当前决策最核心的上下文层。

### Layer C：Working Set（工作集层）
明确维护当前真正相关对象：

- 最近读过的文件
- 最近写过的文件
- 当前计划涉及的文件
- 最近重复动作
- 当前 pending approval 的对象

Working Set 是下一阶段最重要的新增层。

### Layer D：Compact Summary（压缩摘要层）
对旧过程做摘要，而不是保留全文。

建议保留：
- 已完成事项
- 关键结论
- 文件修改摘要
- 核心验证结果
- 审批结果摘要

### Layer E：Recent Dynamic Observations（最新动态层）
仅保留最新、最影响当前决策的内容：
- 最近一个 tool result
- 最近一个 verify result
- 最近一次 summary
- 最近一次用户回复 / 批准 / 拒绝

---

## 3.3 需要新增的模块

### 新增 `context/working_set.py`
定义：

```python
from dataclasses import dataclass

@dataclass
class WorkingSet:
    recently_read_files: list[str]
    recently_written_files: list[str]
    active_files: list[str]
    repeated_actions: list[dict]
```

并提供：
- `record_read(path)`
- `record_write(path)`
- `record_action(action)`
- `summarize()`

### 新增 `context/context_layers.py`
定义统一上下文对象：

```python
from dataclasses import dataclass

@dataclass
class PromptContext:
    query_state_projection: str
    working_set_summary: str
    compact_memory_summary: str
    recent_observations: str
```

### 新增 `memory/session_summary_service.py`
负责将旧历史压缩为摘要，避免 prompt 中堆积原始 tool outputs。

---

## 3.4 修改 `context/context_service.py`

### 当前问题
当前 ContextService 更像 recent history 拼装器。

### 升级目标
改成真正的分层构造器：

```python
class ContextService:
    async def build_context(self, session, turn, state) -> PromptContext:
        ...
```

### 必须实现的构建步骤
1. `build_query_state_projection(state)`
2. `build_working_set(session, state)`
3. `build_compact_memory_summary(session)`
4. `build_recent_observations(session, state)`
5. 合并为 `PromptContext`

### 为什么要这样改
因为 ContextService 不应只负责“截断”，而应负责“组织工作记忆”。

---

## 3.5 Compact 策略建议

### Micro Compact
对长工具输出做轻量裁剪：
- bash 输出节选
- 长 read_file 结果可截断显示，但需保留全文访问策略
- 重复 read_file 结果可折叠为“已重复读取 N 次”

### Task Compact
当一个 plan 子任务阶段性完成时，生成：
- 子任务摘要
- 修改文件列表
- 验证结果摘要

### Session Compact
当 session 过长时，将旧历史折叠成长期摘要块。

---

## 3.6 验收标准
完成后，系统应满足：

- prompt 不再只依赖 recent history
- 能显式告诉模型当前 working set
- 重复读/写结果不再全文堆积
- 已完成过程能被摘要保留
- ContextService 能产出结构化 PromptContext

---

# 4. 主线二：工具 Batch 化与并行调度

## 4.1 升级目标

从当前的单 action 串行内核升级为：
- 支持 batch tool call
- 支持只读工具并行
- 为未来多文件写入并行打基础

### 注意
第一阶段只做：
- `read_file`
- `list_dir`
- `grep`

这类无冲突工具的 batch/parallel 执行。  
`write_file` 等写入工具暂不并行，只为后续设计调度机制。

---

## 4.2 为什么 state 还不够

当前有 QueryState，但 kernel 仍然是：

```text
一步 -> 一个 action -> 一个结果
```

要支持并行，必须引入新的“任务层”概念，而不是只靠 state。

---

## 4.3 新增任务调度模型

### 新增 `scheduler/task_spec.py`

```python
from dataclasses import dataclass

@dataclass
class TaskSpec:
    task_id: str
    tool_name: str
    args: dict
    deps: list[str]
    conflict_keys: list[str]
    kind: str   # read / write / search / verify / summary
```

### 新增 `scheduler/task_state.py`

```python
from dataclasses import dataclass

@dataclass
class TaskRuntimeState:
    task: TaskSpec
    status: str    # pending / running / completed / failed / waiting_approval
    result: dict | None = None
```

### 新增 `scheduler/task_scheduler.py`

```python
class TaskScheduler:
    async def schedule(self, tasks: list[TaskSpec]) -> list[TaskRuntimeState]:
        ...
```

---

## 4.4 QueryState 扩展

修改 `engine/query_state.py`，增加：

```python
from dataclasses import field

pending_tasks: dict[str, dict] = field(default_factory=dict)
running_tasks: dict[str, dict] = field(default_factory=dict)
completed_tasks: dict[str, dict] = field(default_factory=dict)
failed_tasks: dict[str, dict] = field(default_factory=dict)
```

### 为什么要这样改
因为未来 kernel 需要知道：
- 哪些任务已发出
- 哪些任务正在执行
- 哪些结果已经到达
- 哪些任务还未完成

---

## 4.5 扩展 action schema

修改 `engine/parser.py`，支持：

### 单工具调用
```json
{
  "type": "tool_call",
  "tool": "read_file",
  "args": {"path": "a.py"}
}
```

### 批量工具调用
```json
{
  "type": "tool_batch",
  "actions": [
    {"tool": "read_file", "args": {"path": "a.py"}},
    {"tool": "read_file", "args": {"path": "b.py"}},
    {"tool": "grep", "args": {"pattern": "fit", "path": "."}}
  ]
}
```

### 限制
第一阶段只允许只读安全工具进入 batch。

---

## 4.6 修改 `engine/dispatcher.py`

### 当前问题
dispatcher 当前应只支持单 action。

### 升级目标
增加 `_handle_tool_batch(...)`：

- 将 actions 转为 TaskSpec
- 提交给 TaskScheduler
- 聚合结果
- 返回一个包含所有 task result 的 Transition

例如：

```python
Transition(
    type="continue",
    reason="batch_tools_completed",
    payload={
        "batch_results": {...}
    }
)
```

---

## 4.7 修改 `tools/tool_executor.py`

### 升级目标
支持单工具执行和调度器并发调用两种模式。

### 说明
ToolExecutor 本身不负责调度，它只负责：
- 单工具调用
- hook 审批链
- 返回 ToolResult

TaskScheduler 负责：
- 决定哪些工具并行
- 聚合等待结果
- 处理冲突

---

## 4.8 并行读的实现方式

第一阶段推荐使用：
- `asyncio.gather()` 并发执行只读工具
- 每个 TaskSpec 独立调用 ToolExecutor
- 聚合结果返回 query kernel

### 规则
- `read_file` / `list_dir` / `grep`：允许并行
- `write_file`：仍然串行
- `bash`：默认串行，除非后续明确分级

---

## 4.9 未来的并行写入设计（暂不实现，只预留）

并行写入必须基于 conflict analysis。

### 新增字段
每个 TaskSpec 需要：
```python
conflict_keys = ["file:gaussian_fit.py"]
```

### 规则
- 不同文件的 write 可考虑并行
- 同一文件的 write 不可并行
- read/write 同一文件必须谨慎控制
- approval 必须逐 task 处理

### 当前阶段要求
只预留冲突字段和调度接口，不实现真实并行写。

---

## 4.10 验收标准
完成后，系统应满足：

- parser 支持 tool_batch
- scheduler 能调度只读工具并行
- QueryState 能表达 pending/running/completed tasks
- 批量读多个文件无需多个 step
- 不破坏现有 hook-based approval 机制

---

# 5. 主线三：Prompt 构建体系优化

## 5.1 升级目标

将当前 PromptService 从“单层拼接器”升级为：

> **五层 Prompt Builder**

借鉴 Claude Code 的核心思想：
- 分层
- 按需注入
- 缓存友好
- 规则与能力分离
- 上下文与用户输入分离

---

## 5.2 目标 Prompt 五层结构

### Layer 1：系统核心层（System Core）
固定不变，尽量缓存友好。

包括：
- agent 角色定义
- 行为准则
- 工具使用原则
- 输出 schema 约束
- 非进展行为限制

建议文件：
- `prompts/system_core.md`
- 或 `prompts/system_core.py`

---

### Layer 2：规则层（Rules Layer）
对应项目级和用户级规则。

建议引入：
- `SIMPLE_AGENT.md`：项目级规则
- `rules/*.md`：路径/模块级规则
- 用户级偏好配置（可选）

规则示例：
- 常用命令
- 项目约束
- 文件不可修改规则
- 风格要求
- 测试约束

---

### Layer 3：能力层（Capabilities Layer）
动态注入当前可用动作空间。

包括：
- 当前可用 tools
- 当前可用 kernel actions
- 哪些工具支持 batch
- 哪些工具需要审批
- 哪些 tools 是只读安全工具

这层要服务 batch 调度协议。

---

### Layer 4：上下文层（Context Layer）
来自 `ContextService` 的 PromptContext。

包括：
- QueryState 投影
- working set
- compact memory summary
- recent observations

这层是当前 prompt 最核心的动态部分。

---

### Layer 5：当前输入层（Current Input Layer）
最后一层，变化最大。

包括：
- 当前用户消息
- 当前恢复事件（approval / user reply）
- 当前工具结果摘要（若适用）
- slash/command 类输入（未来可扩展）

---

## 5.3 PromptService 重构方案

修改 `engine/prompt_service.py`：

### 当前问题
当前 PromptService 更像“当前状态 + 上下文 + 工具 + 输出格式”的直接拼接器。

### 升级目标
重构为：

```python
class PromptService:
    def build_action_prompt(self, prompt_context: PromptContext, state: QueryState, user_input: str) -> str:
        ...
```

内部拆为：

```python
build_system_core()
build_rules_layer()
build_capabilities_layer()
build_context_layer()
build_current_input_layer()
assemble_prompt()
```

---

## 5.4 新增 `prompts/` 子模块结构

建议新增：

```text
prompts/
├── system_core.md
├── rules_loader.py
├── capability_prompt.py
├── context_prompt.py
└── action_prompt.py
```

### 职责
- `system_core.md`：固定核心规则
- `rules_loader.py`：加载项目/用户规则
- `capability_prompt.py`：根据 ToolRegistry / kernel tools 构造能力层
- `context_prompt.py`：格式化 PromptContext
- `action_prompt.py`：最终组装

---

## 5.5 Prompt 必须新增的信息

### 当前状态摘要
必须明确告诉模型：
- 当前 mode
- 当前 step/max_steps
- 当前 plan 状态
- 当前 pending 状态
- 当前任务是否有 in-flight tasks

### Working Set
必须明确：
- 最近读过哪些文件
- 最近写过哪些文件
- 当前最相关的对象是什么
- 哪些动作最近重复过

### Non-progress Guard
必须明确：
- 不要重复相同 read
- 写后应优先 verify / summarize / continue，而不是无限 read
- 批量任务结果已给出时不要重复请求同一批次

### Batch Protocol
必须明确：
- 什么时候可以 `tool_batch`
- 哪些工具允许 batch
- batch JSON schema
- 并行执行的限制

---

## 5.6 缓存友好原则

Prompt 要尽量做到：
- 不变部分在前
- 动态部分在后
- 工具定义可摘要
- context 压缩后再注入
- 用户输入最后注入

即使当前 provider 不做真正的 prefix cache，这种结构也会提升 prompt 稳定性。

---

## 5.7 验收标准
完成后，Prompt 构建应满足：

- PromptBuilder 分层清晰
- 系统核心层独立
- 规则层可扩展
- 能力层动态生成
- ContextLayer 来自 PromptContext
- Prompt 显式支持 batch tools 和 progress guard

---

# 6. 三条主线之间的联动关系

## 6.1 Context 管理为 Prompt 提供内容
没有分层 context，就无法构建高质量 prompt。

## 6.2 Prompt 定义工具 batch 协议
没有 prompt 协议，模型无法稳定输出 batch action。

## 6.3 Scheduler 结果反过来进入 Context
批量任务结果必须回到 QueryState 和 PromptContext 中，供下一轮模型决策。

因此：
- 先做 context 分层
- 再做 prompt builder 重构
- 然后接入 batch scheduler
是最自然的顺序。

---

# 7. 建议实施顺序

## Phase 1：Context 分层
1. 新增 `context/working_set.py`
2. 新增 `context/context_layers.py`
3. 新增 `memory/session_summary_service.py`
4. 修改 `context/context_service.py`

## Phase 2：Prompt Builder 重构
5. 新增 `prompts/system_core.md`
6. 新增 `prompts/rules_loader.py`
7. 新增 `prompts/capability_prompt.py`
8. 新增 `prompts/context_prompt.py`
9. 修改 `prompts/action_prompt.py`
10. 修改 `engine/prompt_service.py`

## Phase 3：Batch Tool Schema
11. 新增 `scheduler/task_spec.py`
12. 新增 `scheduler/task_state.py`
13. 新增 `scheduler/task_scheduler.py`
14. 修改 `engine/query_state.py`
15. 修改 `engine/parser.py`
16. 修改 `engine/dispatcher.py`

## Phase 4：接入 query kernel
17. 修改 `engine/query_loop.py`
18. 修改 `tools/tool_executor.py`（支持 scheduler 调用）
19. 调整 `ContextService` / `PromptService` 对批量结果的处理

---

# 8. 最终目标

完成本阶段后，系统应达到：

## 架构层
- Context 不再是 recent-window，而是分层工作记忆
- Prompt 不再是单层拼接，而是五层 Prompt Builder
- query kernel 不再只能单 action 串行推进，而能调度只读 batch tools

## 行为层
- 多文件 read/search 可以一次批量发起
- 模型能感知 working set 与最近进展
- 重复 read / non-progress loop 显著减少
- prompt token 使用更稳定、更经济

## 为未来保留
- 多文件并行写入
- 更复杂冲突调度
- 更强上下文压缩
- sub-agent / skill / rules 体系

---

# 9. 一句话总结

下一阶段的关键不是“再加几个功能”，而是：

> **把 simple_agent 从“状态机驱动的单步 query kernel”升级为“分层 context + 分层 prompt + batch scheduler 驱动的 query runtime”。**

执行者必须围绕这三条主线协同实现，而不是孤立优化某一个模块。
