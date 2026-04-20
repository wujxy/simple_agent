# HOOK_BASED_APPROVAL_PLAN.md

# simple_agent Hook-Based 审批系统优化方案

> 目标：为 `simple_agent` 引入一套仿照 Claude Code 思想的 **Hook-Based 审批系统**，解决当前“批准输入被再次送回模型、导致重复审批/循环审批”的问题。
>
> 本方案面向执行者（如 Claude Code），要求在现有 `SessionRuntime + QueryEngine + QueryState + query_loop + ToolExecutor` 基础上，优化审批链路，而不是推翻当前状态机内核。

---

# 1. 当前问题概述

当前系统已经具备：

- SessionRuntime 常驻运行
- QueryEngine / query_loop 分层
- QueryState + Transition 状态机方向
- ToolExecutor / PolicyService / MemoryService / ContextService 等服务

但审批机制仍存在一个根本问题：

> **审批输入（如 `y`、`/approve`）没有被 runtime 本地消费，而是又流回模型主循环，变成新的普通用户消息。**

## 1.1 当前错误表现
典型错误链路如下：

```text
模型请求 write_file
-> ToolExecutor 检测到需要审批
-> Runtime 提示用户 approve / deny
-> 用户输入 y
-> y 被当成普通 user message
-> 又进入 LLM
-> 模型重新 planning / 重新生成 write_file
-> 再次审批
-> 循环
```

## 1.2 根本原因
审批目前仍然是“对话层行为”，而不是真正的“运行时拦截 + 外部决策 + 本地恢复”。

这说明：

- PolicyService 没有真正进入控制流
- waiting_user_approval 没有成为真实状态
- pending action 没有被本地执行恢复
- 批准输入没有与普通用户输入区分

---

# 2. 优化目标

本次优化的目标不是“让模型更会理解批准输入”，而是：

> **让审批从模型主循环中剥离，成为 ToolExecutor 前的一个独立拦截-评估-审批-回写链路。**

具体来说：

1. 在工具执行前增加 `PreToolUse Hook`
2. Hook 层根据规则决定：
   - allow
   - deny
   - context_required
   - ask
3. ask 时创建审批请求，而不是让模型自己处理
4. 用户批准后，runtime 直接执行 pending action
5. 将执行结果回写给 query loop
6. 审批输入不再进入模型作为普通 user message

---

# 3. 设计原则

## 3.1 模型只负责“想做什么”
模型负责：
- 生成 action
- 选择工具
- 生成 description（必要时）

模型不负责：
- 审批最终判断
- 权限放行
- 审批结果解析

---

## 3.2 Policy / Hook 层负责“允不允许”
Policy/Hook 层负责：
- 风险规则
- 审批要求
- 危险指令拒绝
- 自动批准
- 要求模型补充上下文说明

---

## 3.3 审批输入必须由 runtime 本地消费
`y`、`/approve`、`/deny` 这些输入不应直接进模型。  
它们应该先由 `SessionRuntime` / `QueryEngine.resume_approval()` 消费。

---

## 3.4 批准后直接执行 pending action
批准后不应重新问模型“现在怎么办”。  
正确做法是：

```text
批准
-> 取出 pending action
-> 直接执行
-> 得到 ToolResult
-> 回写 state / memory
-> 继续 query loop
```

---

# 4. 目标架构

```text
LLM 生成 tool_call
-> dispatcher
-> ToolExecutor.execute(...)
-> PreToolUseHookManager.run(...)
-> PolicyEngine.evaluate(...)
   -> allow           -> 执行工具
   -> deny            -> 返回拒绝
   -> context_required-> 要求模型补描述
   -> ask             -> 创建审批请求并 suspend turn

用户 approve/deny
-> SessionRuntime 捕获输入
-> QueryEngine.resume_approval(...)
-> ApprovalService 消费审批结果
-> ToolExecutor.execute(..., approved=True)
-> ToolResult 写回 QueryState / Memory
-> query_loop 继续
```

---

# 5. 需要新增的模块

## 5.1 新增 `hooks/pre_tool_use.py`

### 目的
定义 ToolExecutor 执行前的统一拦截接口。

### 必须实现

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ToolInvocation:
    session_id: str
    turn_id: str
    tool_name: str
    args: dict
    cwd: str | None = None
    description: str | None = None

@dataclass
class HookDecision:
    status: str                 # allow / deny / ask / context_required
    reason: Optional[str] = None
    message: Optional[str] = None
    payload: Optional[dict] = None

class PreToolUseHook:
    async def before_tool_use(self, invocation: ToolInvocation) -> HookDecision:
        raise NotImplementedError
```

### 说明
- `ToolInvocation` 是进入 hook 层的标准对象
- `HookDecision` 是 hook 层唯一输出
- 不允许返回含糊 dict

---

## 5.2 新增 `hooks/hook_manager.py`

### 目的
统一管理和执行 PreToolUse hooks。

### 必须实现

```python
class HookManager:
    def __init__(self, pre_tool_hooks: list[PreToolUseHook]):
        self.pre_tool_hooks = pre_tool_hooks

    async def run_pre_tool_use(self, invocation: ToolInvocation) -> HookDecision:
        for hook in self.pre_tool_hooks:
            decision = await hook.before_tool_use(invocation)
            if decision.status != "allow":
                return decision
        return HookDecision(status="allow")
```

### 说明
第一版保持简单：
- 顺序执行 hooks
- 第一个非 allow 的 decision 立刻返回

---

## 5.3 新增 `policy/policy_engine.py`

### 目的
从简单 `PolicyService.check()` 升级为真正的规则引擎。

### 必须实现

```python
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class PolicyDecision:
    status: Literal["allow", "deny", "ask", "context_required"]
    reason: Optional[str] = None
    approval_message: Optional[str] = None
```

```python
class PolicyEngine:
    def __init__(self, config: dict):
        self.config = config

    async def evaluate(self, invocation: ToolInvocation) -> PolicyDecision:
        ...
```

### 最低要求
- `read_file` / `list_dir` 默认 allow
- `write_file` 默认 ask
- `bash` 默认 ask 或 deny（由配置控制）
- 支持基于工具名的简单规则
- 后续可扩展到命令正则、路径规则

### 说明
这是审批系统的规则中心，不要把规则散落在 QueryLoop 或 ToolExecutor 内部。

---

## 5.4 新增 `approval/approval_store.py`

### 目的
保存审批请求。

### 必须实现

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ApprovalRequest:
    request_id: str
    session_id: str
    turn_id: str
    tool_name: str
    args: dict
    description: str | None
    status: str    # pending / approved / denied / expired
    message: str | None = None

class ApprovalStore:
    def __init__(self):
        self._requests = {}

    def add(self, req: ApprovalRequest) -> None: ...
    def get(self, request_id: str) -> ApprovalRequest: ...
    def update_status(self, request_id: str, status: str) -> None: ...
```

### 说明
第一版使用内存存储即可。

---

## 5.5 新增 `approval/approval_service.py`

### 目的
审批服务，统一管理审批单创建与决策。

### 必须实现

```python
class ApprovalService:
    def __init__(self, store: ApprovalStore):
        self.store = store

    async def create_request(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        args: dict,
        description: str | None,
        message: str | None = None,
    ) -> ApprovalRequest:
        ...

    async def approve(self, request_id: str) -> ApprovalRequest:
        ...

    async def deny(self, request_id: str) -> ApprovalRequest:
        ...

    async def get(self, request_id: str) -> ApprovalRequest:
        ...
```

### 说明
第一版只做本地 CLI 审批。  
不要一开始就实现浏览器/UI/HTTP/轮询。

---

# 6. 需要修改的模块

## 6.1 修改 `tools/tool_executor.py`

### 当前问题
当前 `ToolExecutor` 只知道：
- registry.get
- policy.check
- execute

它还不是一个真正的“拦截-审批-执行”网关。

### 改造目标
让 ToolExecutor 在真正执行工具前先跑 HookManager。

### 必须修改为如下流程

```python
ToolExecutor.execute(...)
    -> build ToolInvocation
    -> HookManager.run_pre_tool_use(invocation)
    -> if allow: execute tool
    -> if deny: return denied ToolResult
    -> if context_required: return context-required ToolResult
    -> if ask: create approval request and return approval-required ToolResult
```

### 推荐返回结构
建议扩展 `ToolResult`，不要把审批语义埋进 metadata：

```python
@dataclass
class ToolResult:
    success: bool
    tool_name: str
    args: dict
    output: str | None = None
    error: str | None = None
    metadata: dict | None = None

    approval_required: bool = False
    approval_request_id: str | None = None
    approval_message: str | None = None

    context_required: bool = False
    context_message: str | None = None
```

### 必须新增执行入口
```python
async def execute(self, ..., approved: bool = False) -> ToolResult:
    ...
```

#### 规则
- `approved=False`：正常走 Hook/Policy
- `approved=True`：跳过 ask，不再重复审批

### 为什么必须这样改
因为当前 bug 的根因之一就是：
批准后又用普通执行入口走了一次 ask 流程。

---

## 6.2 修改 `runtime/session_runtime.py`

### 当前问题
当前 runtime 没有把审批输入与普通用户输入分开。

### 必须修改
`handle_user_input(session_id, text)` 必须先检查 active turn 状态：

```python
if active_turn.mode == "waiting_user_approval":
    return await query_engine.resume_approval(session_id, text)

if active_turn.mode == "waiting_user_input":
    return await query_engine.resume_user_input(session_id, text)

return await query_engine.submit_message(session_id, text)
```

### 重要规则
当 `waiting_user_approval` 时：
- 不要把原始输入当作普通 user message 记录进 session history
- 不要把 `y` 直接送给模型

### 为什么必须这样改
这是修复审批循环的第一关键点。

---

## 6.3 修改 `engine/query_engine.py`

### 当前问题
当前 `resume_turn()` 逻辑很可能仍然把批准输入当成普通用户文本。

### 必须拆成两个恢复入口

#### `resume_user_input(session_id, text)`
用于恢复：
- `waiting_user_input`

行为：
1. 把用户文本写入 session history
2. 写入 memory
3. 重建 QueryState
4. 继续 query_loop

---

#### `resume_approval(session_id, text)`
用于恢复：
- `waiting_user_approval`

行为：
1. 不把原始 `text` 写成普通用户消息
2. 解析 approve / deny
3. 获取 `pending_action` 与 `approval_request_id`
4. 如果 approve：
   - `approval_service.approve(request_id)`
   - `tool_executor.execute(..., approved=True)`
   - 写入 ToolResult
   - 清除 pending_action
   - mode -> running
   - 继续 query_loop
5. 如果 deny：
   - `approval_service.deny(request_id)`
   - 注入一条系统/工具拒绝消息
   - 清除 pending_action
   - mode -> running
   - 继续 query_loop

### 必须增加 helper
```python
def parse_approval_response(text: str) -> bool | None:
    ...
```

### 第一版建议协议
只支持：
- `/approve`
- `/deny`
- `y`
- `n`

不要第一版就做复杂自然语言判断。

### 为什么必须这样改
因为批准/拒绝属于 runtime 事件，不是模型语义输入。

---

## 6.4 修改 `engine/query_loop.py`

### 当前问题
query_loop 虽然已经状态机化，但 approval/context_required 还没有被当成内核级 transition。

### 必须修改 dispatch 结果到 transition 的逻辑

#### 对于 `approval_required`
返回：

```python
Transition(
    type="wait_user_approval",
    reason="tool_requires_approval",
    message=tool_result.approval_message,
    payload={
        "request_id": tool_result.approval_request_id,
        "tool_name": tool_result.tool_name,
        "args": tool_result.args,
    },
)
```

#### 对于 `context_required`
不要直接 ask approval。  
应将其视为“要求模型补充理由”的反馈，写回 state/memory，然后继续 loop。

例如：
- 写一条 system note
- 提示模型必须重新调用同一动作并附带 description

### 为什么必须这样改
因为这两种情况本质上都不是普通 ToolResult，需要进入状态机语义。

---

## 6.5 修改 `engine/query_state.py`

### 当前问题
仅有 `pending_action` 还不够表达审批恢复。

### 需要增加字段
建议增加：

```python
pending_action: PendingAction | None = None
approval_request_id: str | None = None
approval_required: bool = False
```

或者将 `approval_request_id` 放进 `pending_action.payload` 中。

### 推荐
为清晰起见，放进 `pending_action.payload` 即可：

```python
PendingAction(
    type="user_approval",
    payload={
        "tool_name": ...,
        "args": ...,
        "request_id": ...,
    },
    message="Tool 'write_file' requires approval",
)
```

---

## 6.6 修改 `sessions/schemas.py`

### 当前问题
TurnState 需要能够持久化审批等待态。

### 必须新增/确保存在字段
- `mode`
- `pending_action`
- `waiting_message`

### 关键要求
每次 `apply_transition()` 后，必须同步 QueryState -> TurnState。

### 为什么必须这样改
否则 suspend 后 restart 或继续输入时，runtime 不知道该恢复什么。

---

## 6.7 修改 `policy/policy_service.py`

### 当前问题
如果还保留旧版 PolicyService，仅返回简单 allow/ask/deny dict，会和新的 HookManager / PolicyEngine 语义冲突。

### 处理方式
可以有两种方案：

#### 方案 A（推荐）
让 `PolicyService` 退化为 `PolicyEngine` 的薄包装。

#### 方案 B
保留 `PolicyService` 名字，但内部调用 `PolicyEngine.evaluate(...)`

### 关键要求
不要让 QueryLoop 直接依赖简单 dict 风格的旧 policy 结果。

---

# 7. 新增一个本地 CLI 审批适配器（可选但推荐）

## 7.1 新增 `approval/cli_approval_adapter.py`

### 目的
提供简单本地审批体验，而不需要浏览器/HTTP 服务。

### 实现思路
它不负责真正执行 approve/deny，只负责将审批单提示信息格式化给用户。

例如：
```python
class CLIApprovalAdapter:
    def format_prompt(self, req: ApprovalRequest) -> str:
        return (
            f"Tool '{req.tool_name}' requires approval.\n"
            f"Args: {req.args}\n"
            "Type '/approve' or 'y' to approve, anything else to deny."
        )
```

### 说明
第一版足够了。  
浏览器审批和轮询完全可以后置。

---

# 8. 对现有 Query Kernel 状态机的配合要求

本次 hook-based 审批优化不是替代状态机内核，而是与它协同：

- `QueryState` 负责表示等待态
- `Transition` 负责切换到 `waiting_user_approval`
- `QueryEngine.resume_approval()` 负责恢复
- `ToolExecutor` 负责真正拦截
- `PolicyEngine` 负责决策
- `ApprovalService` 负责审批单状态

所以：

> **审批机制是 Query Kernel 的一个扩展子系统，不是另起炉灶。**

---

# 9. 强制实施顺序

执行者必须按以下顺序实现。

## Phase 1：Hook / Policy 基础
1. 新增 `hooks/pre_tool_use.py`
2. 新增 `hooks/hook_manager.py`
3. 新增 `policy/policy_engine.py`

## Phase 2：审批存储与服务
4. 新增 `approval/approval_store.py`
5. 新增 `approval/approval_service.py`
6. 可选新增 `approval/cli_approval_adapter.py`

## Phase 3：工具网关改造
7. 修改 `tools/tool_executor.py`

## Phase 4：状态机接入
8. 修改 `engine/query_loop.py`
9. 修改 `engine/query_state.py`
10. 修改 `sessions/schemas.py`

## Phase 5：runtime 恢复路径
11. 修改 `engine/query_engine.py`
12. 修改 `runtime/session_runtime.py`

## Phase 6：收尾统一
13. 修改 `policy/policy_service.py`

---

# 10. 必须通过的验证用例

## 10.1 基础审批
- 模型请求 `write_file`
- hook 决策为 ask
- 生成审批单
- turn 进入 `waiting_user_approval`

## 10.2 批准后恢复
- 用户输入 `/approve` 或 `y`
- runtime 不把该输入送进模型
- pending write_file 直接执行
- tool_result 回写
- query_loop 继续

## 10.3 拒绝后恢复
- 用户输入 `/deny` 或 `n`
- runtime 不把该输入送进模型
- 注入“用户拒绝该操作”的结果
- query_loop 继续
- 模型有机会选择替代方案

## 10.4 禁止循环审批
- 同一个 pending_action 在 approve 后不能再次 ask
- 必须通过 `approved=True` 或等效机制绕过重复 ask

## 10.5 context_required 两段式流程
- 第一次 tool_call 缺少 description
- hook 返回 `context_required`
- 模型补充说明后重试
- 然后再进入 ask 或 allow

---

# 11. 执行者禁止事项

执行者不得：

- 继续把审批输入当作普通用户消息送回模型
- 在 `query_loop.py` 内直接处理 approve/deny 文本
- 让批准后的 pending action 再次走普通 ask 流程
- 把 hook/policy/approval 逻辑散落到多个 if/else 中
- 一开始就实现复杂浏览器审批，而忽略本地闭环正确性

---

# 12. 一句话总结

本次优化的本质不是“修一个审批 bug”，而是：

> **把工具审批从 query loop 的文本化处理升级为一条真正的 Hook-Based 运行时链路：PreToolUse 拦截 → Policy/Rule 决策 → ApprovalService 挂起 → Runtime 本地恢复 → 直接执行 pending action → ToolResult 回写 Query Kernel。**

执行者必须严格遵守这个分层，确保审批结果不再流回模型成为普通用户输入。
