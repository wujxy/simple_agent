# QUERY_KERNEL_STATE_MACHINE_PLAN.md

# simple_agent Query Kernel 状态机升级方案

> 本文档面向执行者（如 Claude Code），用于指导 `simple_agent` 从“服务化但仍偏线性的 query loop”升级为“State + Transition 驱动的 Query Kernel”。
> 重点说明：
> 1. 当前程序的问题
> 2. 要怎么升级
> 3. 为什么要这样升级
> 4. 各文件如何修改

---

# 1. 升级目标

当前 `simple_agent` 已经完成：

- 程序常驻
- SessionRuntime 存在
- QueryEngine 与 query_loop 已拆开
- ToolExecutor / LLMService / MemoryService / ContextService 已服务化

但核心问题仍然存在：

> **query_loop 仍然在“线性地决定完整流程”，而不是依据显式工作状态推进。**

因此，本次升级目标是：

- 引入 `QueryState`
- 引入 `Transition`
- 让 query_loop 从“流程函数”变成“状态机内核”
- 将 `plan / verify / summary / ask_user` 从 loop 的硬编码流程中解放出来，统一为可调用能力
- 让 `ask_user / approval` 成为真正的 suspend / resume 机制

---

# 2. 当前程序的问题

## 2.1 query_loop 仍然“决定一切”
当前 query_loop 虽然独立成文件，但它依然内部决定：

- 什么时候 plan
- 什么时候 verify
- 什么时候 summary
- 工具执行后如何推进
- ask_user 后是否真正等待

### 问题本质
它仍更像：

```text
build context
-> build prompt
-> call llm
-> parse action
-> if tool_call then execute
-> if finish then verify
-> if done then summary
```

这是线性流程脚本思维，不是状态机思维。

### 后果
- 模型没有真正掌握工作模式切换权
- plan / verify / summary 被 loop 硬编码
- query_loop 容易继续膨胀
- 后续增加 recovery / approval / hooks / budget 会越来越困难

---

## 2.2 缺少显式 QueryState
当前系统主要依赖：

- SessionState
- TurnState
- 局部变量
- tool result
- recent memory

来隐式推动 query loop。

### 问题本质
缺少一个专门的“单轮 query 内核状态”对象。

### 后果
- loop 无法显式表达“当前为什么继续”
- 无法表达“当前是在 waiting_user_input 还是 waiting_user_approval”
- 无法表达“当前是否在 verify 之后继续”
- 无法表达“当前 pending 的动作是什么”
- 状态只能散落在多个对象和 if 分支中

---

## 2.3 缺少显式 Transition
当前 loop 主要通过：

- `continue`
- `return`
- `if/else`

推进控制流。

### 问题本质
没有把“这一轮结束后系统应该转移到什么状态”抽象成显式对象。

### 后果
- loop 的行为难以推理
- 状态推进逻辑分散
- ask_user / approval / finish / failure 缺乏统一语义
- 调试和测试困难

---

## 2.4 plan / verify / summary 被写死在 loop 里
目前这三种能力仍然更像“流程节点”，而不是“模型可以主动调用的能力”。

### 问题本质
模型只能在小范围内决定 action，而不能真正决定：

- 现在是否应该先 planning
- 现在是否需要 verify
- 现在是否需要阶段性 summarize

### 后果
- 模型自治能力不足
- loop 与业务流程强耦合
- 后续无法自然演进到更成熟的 agent kernel

---

## 2.5 ask_user 没有真正实现 suspend / resume
当前 ask_user 和 policy 的 ask 行为虽然存在，但并没有真正进入 runtime 状态机。

### 问题本质
`ask_user` 仍然更像“返回一句消息”，而不是真正的系统等待态。

### 后果
- PolicyService 看起来存在，但没有真正控制执行流
- 用户下一次输入无法被识别为“恢复挂起 turn”
- 审批与普通追问没有区分
- session runtime 没有真正的暂停/恢复能力

---

# 3. 为什么必须升级成 State + Transition 模式

## 3.1 query loop 的职责应该是“推进状态”，不是“规定流程”
更成熟的 query kernel 不是写死：
- 先做 A
- 再做 B
- 再做 C

而是：
- 读取当前状态
- 执行一轮动作
- 产生 transition
- 更新状态
- 下一轮根据新状态继续

---

## 3.2 模型应当决定工作模式，框架只提供能力
运行时应该提供：
- `plan`
- `verify`
- `summarize`
- `ask_user`
- `tool_call`

这些能力，但不应该把这些能力写死成固定流程。

---

## 3.3 ask_user / approval 必须进入控制流
如果 approval 只是返回一条文本，而不是改变 turn 状态，那 PolicyService 只是装饰，不是真正的策略系统。

---

## 3.4 未来高级特性都依赖状态机基础
后续如果要支持：
- streaming
- interruption
- user approval
- background turn recovery
- hooks
- retries / recovery
- sub-agent

都必须依赖统一的：
- State
- Transition
- pending action
- suspend / resume

---

# 4. 升级后的目标结构

升级后，query kernel 应满足：

```text
QueryEngine.submit_message()
    -> 构造 QueryState
    -> 调用 query_loop(state, deps)
        -> 每轮:
            read state
            build context
            call llm
            parse action
            dispatch action
            get transition
            apply transition to state
        -> return QueryLoopResult
```

---

# 5. 新增与修改的核心概念

## 5.1 QueryState
表达“当前 query 内核处于什么状态”。

## 5.2 Transition
表达“这一轮结束后应该如何转移”。

## 5.3 PendingAction
表达“当前有一个尚未完成、等待用户输入或审批的动作”。

## 5.4 Kernel Tools
将：
- plan
- verify
- summarize
- ask_user

统一作为“可调用能力”加入 action 空间。

---

# 6. 逐文件修改方案

## 6.1 新增 `engine/query_state.py`

### 当前问题
当前没有专门的 query 内核状态对象，loop 状态散落在：
- TurnState
- SessionState
- 局部变量
- memory
中。

### 需要新增的内容

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PendingAction:
    type: str
    payload: dict

@dataclass
class QueryState:
    session_id: str
    turn_id: str

    step_count: int = 0
    max_steps: int = 20

    mode: str = "running"   # running / waiting_user_input / waiting_user_approval / completed / failed

    current_plan: Optional[dict] = None
    last_action: Optional[dict] = None
    last_tool_result: Optional[dict] = None
    last_verify_result: Optional[dict] = None
    last_summary: Optional[str] = None

    pending_action: Optional[PendingAction] = None
    waiting_message: Optional[str] = None
    transition_reason: Optional[str] = None

    metadata: dict = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.mode in {"completed", "failed"}

    def can_continue(self) -> bool:
        return self.mode == "running" and self.step_count < self.max_steps
```

### 为什么要这样改
因为必须把“单轮 query 的状态”聚合成一个对象，避免 query_loop 继续依赖分散状态。

---

## 6.2 新增 `engine/transitions.py`

### 当前问题
当前 loop 主要靠 `continue/return` 推进，没有显式 transition 语义。

### 需要新增的内容

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Transition:
    type: str   # continue / wait_user_input / wait_user_approval / completed / failed
    reason: str
    message: Optional[str] = None
    payload: Optional[dict] = None
```

并实现：

```python
def apply_transition(state: QueryState, transition: Transition) -> QueryState:
    ...
```

### 为什么要这样改
因为 query kernel 的推进应该由“状态转移”统一表达，而不是散落在多个 if/else 中。

---

## 6.3 修改 `sessions/schemas.py`

### 当前问题
TurnState 不能表达真正的等待态。

### 需要修改
给 `TurnState` 增加字段：

```python
mode: str                        # running / waiting_user_input / waiting_user_approval / completed / failed
pending_action: dict | None
waiting_message: str | None
```

### 为什么要这样改
因为 `ask_user` 和 approval 需要作为 session/runtime 层的真实状态存在，而不是临时文本。

---

## 6.4 修改 `engine/parser.py`

### 当前问题
模型当前的 action 空间过窄，不能自然表达内核能力。

### 需要修改
将 action 空间扩展为两种可选方案中的一种：

### 方案 A：显式 action type
```python
type: Literal[
    "tool_call",
    "plan",
    "replan",
    "verify",
    "summarize",
    "ask_user",
    "finish"
]
```

### 方案 B：统一工具化（推荐）
全部都作为 tool_call：

```python
{
  "type": "tool_call",
  "tool": "plan",
  "args": {...}
}
```

内核能力包括：
- `plan`
- `verify`
- `summarize`
- `ask_user`

### 推荐
采用**统一工具化方案**，避免 action 类型继续膨胀。

### 为什么要这样改
因为模型要能主动决定工作模式，而不是只会触发外部工具。

---

## 6.5 新增 `engine/kernel_tools.py`

### 当前问题
plan / verify / summary / ask_user 还是 loop 的硬编码分支。

### 需要新增
实现以下“内核工具”：

- `PlanTool`
- `VerifyTool`
- `SummaryTool`
- `AskUserTool`

示例：

```python
class PlanTool:
    name = "plan"
    async def run(self, session, state, planner):
        plan = await planner.replan(session, state)
        return {"success": True, "plan": plan}

class VerifyTool:
    name = "verify"
    async def run(self, session, state, verifier):
        result = await verifier.verify(session, state)
        return {"success": True, "verify_result": result}

class SummaryTool:
    name = "summarize"
    async def run(self, session, state, prompt_service, llm_service):
        prompt = prompt_service.build_summary_prompt(session, state, {})
        summary = await llm_service.generate(prompt)
        return {"success": True, "summary": summary}

class AskUserTool:
    name = "ask_user"
    async def run(self, session, state, message: str):
        return {
            "success": True,
            "waiting": True,
            "message": message
        }
```

### 为什么要这样改
因为这些能力不是“外部世界操作”，但它们是运行时可调用能力，应该和工具系统统一。

---

## 6.6 修改 `tools/registry.py`

### 当前问题
工具系统目前只有外部工具，没有内核能力工具。

### 需要修改
在 ToolRegistry 注册时加入：

- `PlanTool`
- `VerifyTool`
- `SummaryTool`
- `AskUserTool`

### 为什么要这样改
因为 query loop 不应该继续特判这几个能力。

---

## 6.7 修改 `tools/tool_executor.py`

### 当前问题
PolicyService 的 `ask` 没有真正进入控制流，ask_user 也没有 suspend。

### 需要修改
执行流程改为：

1. registry.get(tool)
2. policy_service.check(...)
3. 如果 `deny` -> 返回失败结果
4. 如果 `ask` -> 返回结构化的 `approval_required` 结果，不执行工具
5. 如果 `allow` -> 执行工具

增加结果结构：

```python
{
    "success": False,
    "approval_required": True,
    "message": "...",
    "pending_action": {...}
}
```

### 为什么要这样改
因为 policy ask 必须真正阻止执行，并让 runtime 进入等待审批状态。

---

## 6.8 修改 `policy/policy_service.py`

### 当前问题
PolicyService 虽然存在，但没有真正参与状态切换。

### 需要修改
定义：

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class PolicyDecision:
    status: Literal["allow", "ask", "deny"]
    reason: str | None = None
    approval_message: str | None = None
```

`check(...)` 返回 `PolicyDecision` 而不是随意 dict。

### 为什么要这样改
因为策略系统必须有清晰、严格的返回语义，才能驱动状态机。

---

## 6.9 重写 `engine/query_loop.py`

### 当前问题
当前 query_loop 仍然是线性流程函数。

### 需要修改
重写为：

```python
async def query_loop(state: QueryState, deps: QueryDeps) -> QueryLoopResult:
    while not state.is_terminal():
        if not state.can_continue():
            transition = Transition(type="failed", reason="max_steps_exceeded")
            state = apply_transition(state, transition)
            break

        context = await deps.context_service.build_context(...)
        prompt = deps.prompt_service.build_action_prompt(...)

        llm_response = await deps.llm_service.generate(prompt)
        action = deps.parser.parse_action(llm_response)

        transition = await dispatch_action(action, state, deps)
        state = apply_transition(state, transition)

    return state_to_result(state)
```

### 必须新增
拆出：

- `dispatch_action(...)`
- `result_to_transition(...)`
- `state_to_result(...)`

### 关键要求
query_loop 不能再写死：
- 先 plan
- finish 后强制 summary
- ask_user 后直接结束

而是：
- action -> result
- result -> transition
- transition -> new state

### 为什么要这样改
因为这是从“流程函数”升级为“状态机内核”的核心。

---

## 6.10 新增 `engine/query_deps.py`

### 当前问题
query_loop 依赖过多服务，参数容易膨胀。

### 需要新增
定义统一依赖容器：

```python
from dataclasses import dataclass

@dataclass
class QueryDeps:
    session_store: object
    session_service: object
    memory_service: object
    context_service: object
    prompt_service: object
    llm_service: object
    tool_executor: object
    planner: object
    verifier: object
    parser: object
    tracing_service: object
```

### 为什么要这样改
因为 query kernel 应该是“state + deps”的形式，而不是长参数列表。

---

## 6.11 修改 `engine/query_engine.py`

### 当前问题
虽然 QueryEngine 已经变薄，但仍然缺少 QueryState 初始化与恢复逻辑。

### 需要修改
`submit_message(...)` 要做：

1. 获取 session
2. 创建 turn
3. 构造 `QueryState`
4. 记录用户消息到 session/memory
5. 调用 `query_loop(state, deps)`
6. 根据结果更新 turn/session

同时新增：

```python
async def resume_waiting_turn(self, session_id: str, user_text: str) -> QueryLoopResult:
    ...
```

用于恢复：
- `waiting_user_input`
- `waiting_user_approval`

### 为什么要这样改
因为 QueryEngine 现在不只是 turn 入口，还要成为“挂起 turn 的恢复入口”。

---

## 6.12 修改 `runtime/session_runtime.py`

### 当前问题
Runtime 目前只能把用户输入当成“新 turn”，不能把输入当成“恢复事件”。

### 需要修改
`handle_user_input(...)` 改成：

1. 先检查当前 session 是否有 active turn
2. 如果 active turn 是：
   - `waiting_user_input` -> 恢复该 turn
   - `waiting_user_approval` -> 解析 approve/deny 后恢复
   - 否则 -> 创建新 turn

新增方法：
- `handle_approval_response(...)`
- `handle_user_reply(...)`

### 为什么要这样改
因为 session runtime 必须支持真正的 suspend / resume。

---

## 6.13 修改 `engine/verifier.py`

### 当前问题
verify 仍然更像 loop 的硬编码流程。

### 需要修改
保留 `Verifier` 服务，但把调用权交给模型工具化流程。

### 特别说明
可以保留一个 runtime-level 最终 verify gate：
- 模型可以主动调用 `verify`
- 但 `finish` 时 runtime 仍可做最终验证

### 为什么要这样改
因为要兼顾：
- 模型自治
- 最终防自欺保障

---

## 6.14 修改 `engine/planner.py`

### 当前问题
planning 还是 loop 逻辑的一部分。

### 需要修改
Planner 只保留：
- `plan(...)`
- `replan(...)`

由 `PlanTool` 调用，而不是由 loop 主动决定“现在先 planning”。

### 为什么要这样改
因为 planning 应是能力，不是固定流程节点。

---

## 6.15 修改 `engine/prompt_service.py`

### 当前问题
prompt 还没有围绕“状态机内核”设计。

### 需要修改
`build_action_prompt(...)` 需要接收：

- QueryState
- 当前 context
- 可用工具（包括 kernel tools）

并明确告诉模型：
- 你可以调用这些工具
- 你可以 ask_user
- 你可以 verify / summarize / replan
- 当前 state 是什么

### 为什么要这样改
因为模型必须看见“当前工作状态”和“可用转移能力”。

---

# 7. 实施顺序（强制）

执行者必须按以下顺序改，不能跳步。

## Phase 1：状态机基础
1. 新增 `engine/query_state.py`
2. 新增 `engine/transitions.py`
3. 修改 `sessions/schemas.py`
4. 新增 `engine/query_deps.py`

## Phase 2：能力工具化
5. 修改 `engine/parser.py`
6. 新增 `engine/kernel_tools.py`
7. 修改 `tools/registry.py`

## Phase 3：策略与等待态
8. 修改 `policy/policy_service.py`
9. 修改 `tools/tool_executor.py`

## Phase 4：内核重写
10. 重写 `engine/query_loop.py`
11. 修改 `engine/query_engine.py`

## Phase 5：runtime 恢复机制
12. 修改 `runtime/session_runtime.py`

## Phase 6：配套调整
13. 修改 `engine/planner.py`
14. 修改 `engine/verifier.py`
15. 修改 `engine/prompt_service.py`

---

# 8. 升级后的目标行为

升级完成后，系统应满足：

## 8.1 query loop 不再决定固定流程
而是依据 QueryState 推进。

## 8.2 模型可以主动调用：
- `plan`
- `verify`
- `summarize`
- `ask_user`

## 8.3 ask_user 成为真正等待态
用户下一次输入不一定开启新 turn，而可能恢复旧 turn。

## 8.4 policy ask 真正阻止工具执行
并进入 `waiting_user_approval` 状态。

## 8.5 QueryEngine 真正成为“query wrapper”
而不是 loop 再膨胀回去。

---

# 9. 一句话总结

本次升级的核心不是“再加几个服务”，而是：

> **把 query_loop 从“线性服务调用流程”升级成“QueryState + Transition 驱动的 Query Kernel”，并把 plan / verify / summary / ask_user 全部纳入统一能力空间。**

执行者必须严格遵守这个目标，不得将逻辑重新塞回 `QueryEngine` 或在 `query_loop.py` 中继续写死流程。
