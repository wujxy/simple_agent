# simple_agent 成熟 Agent 框架升级计划

> 目标：将当前学习式源码形态的 `simple_agent` 升级为更稳定、可观测、可扩展的 agent runtime/framework。
>
> 本计划优先解决 agent 的“反射神经”问题：Prompt、Parser、Dispatcher、Tool Result、Memory/Context 必须共享同一套运行协议。只有动作协议稳定，mode 策略、事件流、compact 和框架化能力才有可靠地基。

---

# 1. 总体判断

当前 `simple_agent` 已具备 agent runtime 的雏形：

- `query_loop` 作为执行循环
- `QueryState + Transition` 作为状态推进方向
- `ToolExecutor + ToolRegistry` 作为工具层
- `MemoryService + ContextService` 作为上下文层
- `ApprovalService + HookManager` 作为审批/安全层
- `TaskScheduler` 作为 batch tool 并行调度入口

但它仍然更像“学习式源码”，不是成熟框架。最主要的问题不是工具数量不够，而是运行协议不够稳定：

```text
Prompt 约定动作格式
-> Parser 解析成 AgentAction
-> Dispatcher 按字段读取 action
-> ToolExecutor 执行工具
-> ToolResult 写入 Memory/Context
-> 下一轮 Prompt 反馈给 LLM
```

这条链路只要任意一段字段约定不一致，agent 就会出现“模型以为自己执行了，但 runtime 实际没执行”的情况。典型表现是：

- tool_batch 顶层 `actions` 没有进入 `action.args`
- dispatcher 得到 empty batch
- LLM 下一轮继续尝试读文件
- step 被空转耗尽

因此升级顺序必须先协议化，再策略化，再可观测化。

---

# 2. 五阶段路线图

## Phase 1: Runtime Action/Tool Contract 统一

### 目标

建立稳定的 action/tool/result 协议，保证 Prompt、Parser、Dispatcher、Memory、Context 对字段含义完全一致。

这是第一优先级。

### 核心问题

当前系统大量依赖通用 `args: dict` 传递隐式结构：

- `tool_call` 使用 `tool + args`
- `tool_batch` prompt 使用顶层 `actions`
- dispatcher 使用 `action.args["actions"]`
- memory/context 对 tool result 字段做部分投影

这种方式灵活，但协议边界模糊，容易导致 runtime 与 LLM 断联。

### 关键改动

1. 引入强类型 action schema。

建议将当前单一 `AgentAction` 拆为显式类型：

```python
class ToolCallAction(BaseModel):
    type: Literal["tool_call"]
    reason: str = ""
    tool: str
    args: dict = Field(default_factory=dict)

class ToolBatchItem(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    depends_on: list[int | str] = Field(default_factory=list)

class ToolBatchAction(BaseModel):
    type: Literal["tool_batch"]
    reason: str = ""
    actions: list[ToolBatchItem]

class PlanAction(BaseModel):
    type: Literal["plan"]
    reason: str = ""

class ReplanAction(BaseModel):
    type: Literal["replan"]
    reason: str = ""

class VerifyAction(BaseModel):
    type: Literal["verify"]
    reason: str = ""

class SummarizeAction(BaseModel):
    type: Literal["summarize"]
    reason: str = ""

class AskUserAction(BaseModel):
    type: Literal["ask_user"]
    reason: str = ""
    message: str

class FinishAction(BaseModel):
    type: Literal["finish"]
    reason: str = ""
    message: str
```

2. Parser 只负责“LLM JSON -> 强类型 action”。

Parser 不应该让 dispatcher 猜字段位置。合法 action 必须在 parse 后进入标准结构。

3. Dispatcher 只消费强类型 action。

`_handle_tool_batch` 应读取 `action.actions`，不再读取 `action.args["actions"]`。

4. ToolResult 做标准 projection。

每个 tool result 应稳定包含：

- `tool_name`
- `ok`
- `status`
- `summary`
- `facts`
- `data`
- `error/errors`
- `changed_paths`
- `memory`
- `artifacts`
- `display`
- `diagnostics`
- `metadata`

5. Batch result 做聚合反馈。

`tool_batch` 的整体结果至少包含：

- `total_tasks`
- `completed`
- `failed`
- `skipped`
- `files_read`
- `truncated_files`
- `errors`
- `references`
- `summary`

这样下一轮 prompt 能明确知道哪些文件已经读过，避免重复读取。

### 验收标准

- Prompt 示例中的每种 action 都能被 parser 正确解析。
- Parser 输出的 action 能被 dispatcher 直接消费。
- `tool_batch` 顶层 `actions` 不再丢失。
- empty batch 不再静默消耗 step，应变成协议错误或 recoverable error。
- 每个 action type 有单元测试。
- 每个 tool result projection 有单元测试。
- 至少有一个集成测试覆盖：

```text
list_dir -> tool_batch(read_file x N) -> summarize/finish
```

---

## Phase 2: Runtime Mode Policy 策略化

### 目标

将 mode 做成 runtime 级别的能力边界，而不是 prompt 风格提示。

mode 决定：

- 是否允许读
- 是否允许写
- 是否允许 bash
- 是否需要审批
- 是否强制规划
- 是否严格 verify
- 最大运行成本和安全边界

### Mode 定义

#### normal mode

默认模式。

- 简单任务可以直接答。
- 允许 read 工具自动执行。
- write/bash 需要审批。
- plan 可用，但默认不主动调用。
- 任务复杂度超过阈值时可主动 plan。

适合：

- 普通问答
- 小型代码阅读
- 低风险文件检查

#### plan mode

用户显式开启，或 API 参数开启。

- agent 必须先判断是否需要 plan。
- 复杂任务生成/维护 plan。
- 每个 runtime step 尽量和 plan step 对齐。
- verify 更严格。
- 修改、多文件理解、长任务必须保留 plan progress。

适合：

- 代码修改
- 多文件理解
- 长任务
- 需要阶段性确认的任务

#### yolo mode

高自主模式。

- 写/bash 默认允许或弱审批。
- agent 可以连续执行。
- 但必须有硬安全边界。

硬边界包括：

- blocked commands
- workspace sandbox
- max cost
- max writes
- max runtime
- max tool calls
- max file write size

### 关键改动

1. 引入 `RunMode`。

```python
class RunMode(str, Enum):
    NORMAL = "normal"
    PLAN = "plan"
    YOLO = "yolo"
```

2. 引入 `ModePolicy`。

```python
class ModePolicy(BaseModel):
    allow_read: bool
    allow_write: bool
    allow_bash: bool
    require_approval_for_write: bool
    require_approval_for_bash: bool
    planning_required: bool
    planning_default: bool
    strict_verify: bool
    max_writes: int | None = None
    max_runtime_seconds: int | None = None
    max_tool_calls: int | None = None
```

3. 在 `TurnState` / `QueryState` 中携带 mode 与 policy。

4. Tool approval、planner、verifier、dispatcher 统一读取同一份 policy。

5. Prompt 只呈现当前 mode 的能力边界，不再独立决定权限。

### 验收标准

- `normal/plan/yolo` 三种 mode 可以通过 CLI/API 参数指定。
- 写/bash 权限由 mode policy 决定。
- yolo mode 即使弱审批，也受硬边界限制。
- plan mode 下复杂任务必须维护 plan。
- mode 行为有测试覆盖。

---

## Phase 3: Runtime Event Stream 与可观测输出

### 目标

将 agent 执行过程从 logger 字符串升级为结构化事件流。

CLI、API、UI、调试器都订阅同一套事件，而不是各自读取内部状态。

### 标准事件

建议统一事件命名：

```text
turn.started
step.started
llm.prompt_built
llm.started
llm.completed
action.parsed
tool.started
tool.progress
tool.completed
memory.updated
context.budget.updated
compact.suggested
compact.started
compact.completed
approval.required
step.completed
turn.completed
```

### 事件结构

```python
class RuntimeEvent(BaseModel):
    event: str
    session_id: str
    turn_id: str
    step: int | None = None
    timestamp: float
    payload: dict = Field(default_factory=dict)
```

### CLI 显示目标

CLI 应能实时展示：

```text
[step 3/20] tool_batch: read_file x 12
  running: 8
  completed: 4
  failed: 0

context: 18.4k / 32k tokens, 57%
memory: 9.2k / 12k chars, compact threshold 80%, 2.4k chars remaining
working set: 14 files tracked, 4 projected
```

### 关键改动

1. 扩展 `EventBus`，支持结构化 runtime events。
2. `query_loop` 每个 step 发事件。
3. `PromptService` 发 prompt budget 事件。
4. `LLMService` 发 request/response 事件。
5. `ToolExecutor` / `TaskScheduler` 发 tool progress 事件。
6. `MemoryService` / `ContextService` 发 budget 与 compact 事件。
7. CLI 改为事件订阅式显示。

### 验收标准

- 不看 debug log，也能知道当前 step 在做什么。
- batch tool 可以显示 running/completed/failed。
- context/memory 预算可见。
- approval required 可实时显示。
- 事件流可被测试和快照验证。

---

## Phase 4: Budget-Aware Context 与 LLM Compact

### 目标

将 context/memory 从“最近窗口 + 简单裁剪”升级为预算感知的工作记忆系统，并使用 `LLMService` 做语义压缩。

### 核心设计

上下文分为：

- hot memory：最近 N 个 step 原样保留。
- warm memory：LLM compact 后的结构化摘要。
- cold memory：只保留索引、引用和必要 metadata。
- working set：当前任务真正相关的文件/grep/修改/失败/验证。
- artifact snapshot：关键文件和 shell 结果的短投影。

### LLM Compact 输出结构

建议 compact 输出结构化 JSON：

```json
{
  "task_summary": "...",
  "completed_steps": [],
  "files_read": [],
  "important_facts": [],
  "decisions": [],
  "open_questions": [],
  "risks": [],
  "next_recommended_action": "..."
}
```

### 关键改动

1. 引入 `ContextBudget`。

追踪：

- prompt chars/tokens
- memory chars/tokens
- tool output chars
- working set projected files
- compact threshold
- remaining budget

2. `CompactService` 注入 `LLMService`。

当前 rule-based compact 保留为 fallback。

3. compact 前后发事件：

- `compact.suggested`
- `compact.started`
- `compact.completed`

4. 增加 read coverage ledger。

记录：

- 已读文件
- 读取行范围
- 是否 truncated
- content hash
- last read step

这对“多文件阅读后总结”尤其重要，可以避免 LLM 反复读同一批文件。

### 验收标准

- memory 接近阈值时能提示 compact 距离。
- compact 后仍能保留任务关键事实。
- 多文件阅读后，prompt 能清楚展示已读覆盖面。
- LLM 不会因为旧文件内容未投影而误判“没读过”。
- rule-based compact 在 LLM compact 失败时可 fallback。

---

## Phase 5: Framework Hardening、插件化与发布能力

### 目标

将 runtime 从项目内实现升级为可复用 agent 框架。

这一阶段重点不再是单点能力，而是稳定性、扩展性、可测试性和可发布性。

### 关键方向

#### 1. Tool Plugin Protocol

工具应统一提供：

- name
- description
- input schema
- output schema
- capabilities
- approval requirements
- progress event support
- artifact projection
- memory projection

#### 2. Persistent Runtime

session/turn/memory/artifact/approval 状态应支持落盘恢复。

至少支持：

- JSONL 或 sqlite store
- session resume
- interrupted turn resume
- pending approval resume

#### 3. Eval Harness

建立 agent 行为测试，而不只测函数。

示例 eval：

```text
read_project_summary:
  user: "read simple_agent/engine and summarize main loop"
  expected:
    - calls list_dir once
    - calls tool_batch with read_file actions
    - no empty batch
    - finishes within 6 steps
    - summary mentions query_loop/parser/dispatcher/transitions
```

#### 4. Recovery Policies

为常见失败建立恢复策略：

- parse fail
- empty batch
- repeated read
- context overflow
- tool timeout
- approval denied
- verify fail

#### 5. Package/API Boundary

明确框架入口：

- Python API
- CLI
- config
- plugin registry
- event stream
- storage backend

### 验收标准

- 可以作为 package 安装和运行。
- 有清晰 Python API 创建 session/turn。
- 工具可以插件式注册。
- session 可以持久化和恢复。
- 核心 agent 行为有 eval 覆盖。
- 文档包含 mode、tool、memory、event、compact 的使用说明。

---

# 3. 推荐实施顺序

建议严格按以下顺序推进：

1. Phase 1: Runtime Action/Tool Contract
2. Phase 2: Runtime Mode Policy
3. Phase 3: Runtime Event Stream
4. Phase 4: Budget-Aware Context + LLM Compact
5. Phase 5: Framework Hardening

不要先做 yolo mode 或更多工具。当前最影响稳定性的不是能力不足，而是 runtime contract 不稳定。

---

# 4. Phase 1 的立即任务预告

下一步应细化 Phase 1，形成可执行 patch plan。

建议拆成：

1. 定义 action schema。
2. 修改 parser，输出强类型 action。
3. 修改 dispatcher，消费强类型 action。
4. 修改 prompt，使 action JSON 与 schema 完全一致。
5. 修改 query_loop debug/step payload，适配新 action。
6. 聚合 batch result。
7. empty batch 改为 protocol error。
8. 补单元测试和集成测试。

这一阶段完成后，agent 的动作闭环会稳定很多，后续 mode、事件流、compact 才值得继续堆上去。

