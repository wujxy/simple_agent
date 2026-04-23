# Simple Agent 教程

## 项目简介

Simple Agent 是一个基于 LLM 的自主代理框架，能够理解用户意图、制定计划、调用工具执行任务，并自动验证结果。

核心特性：

- **常驻会话**：程序启动后持续运行，支持多轮对话
- **自主规划**：复杂任务自动拆解为多步计划，支持重规划
- **工具调用**：内置文件读写、目录列表、Shell 命令等工具
- **Hook 审批**：基于 Hook 链的工具调用拦截，支持策略检查和人工审批
- **自动验证**：任务完成后自动检查是否真正达成目标

---

## 快速开始

### 1. 安装依赖

```bash
cd simple_agent
pip install -e .
```

### 2. 配置

确保 `ZHIPU_API_KEY` 环境变量已设置：

```bash
export ZHIPU_API_KEY="your-api-key"
```

配置文件位于 `configs/` 目录：

| 文件 | 用途 |
|------|------|
| `configs/model.yaml` | 模型参数（模型名、温度、token 上限） |
| `configs/agent.yaml` | Agent 参数（最大步数、是否启用规划） |
| `configs/policy.yaml` | 权限策略（读写、Shell 是否允许） |

### 3. 启动

```bash
python -m simple_agent.app
```

启动后进入交互模式：

```
Session started: sess_a1b2c3d4e5f6
Type your tasks. Enter '/exit' to quit.

> 写一个 hello world 程序到 /tmp/hello.py

[INFO] query_loop: Step 1/20 [running]
[INFO] tool_executor: Approval required: Tool 'write_file' requires user approval

Tool 'write_file' requires approval. Type '/approve' or 'y' to approve, anything else to deny.
(user) y
[INFO] query_loop: Step 2/20 [running]
...
Agent finished: 已将 hello world 程序写入 /tmp/hello.py

>
```

### 4. 编程调用

如果需要在其他 Python 程序中使用：

```python
import asyncio
from simple_agent.config import load_config
from simple_agent.runtime.session_runtime import SessionRuntime

async def main():
    config = load_config("configs")
    runtime = SessionRuntime(config)
    await runtime.start()

    session_id = await runtime.create_session()

    # 执行任务
    result = await runtime.handle_user_input(session_id, "读取 README.md 的内容")
    print(result.message)    # 输出：Agent 的回复
    print(result.status)     # "completed" | "waiting_user" | "failed"

    # 多轮对话
    result = await runtime.handle_user_input(session_id, "现在把它翻译成英文")
    print(result.message)

    await runtime.stop()

asyncio.run(main())
```

---

## 项目架构

```
simple_agent/
├── app.py                          # 程序入口（常驻交互循环）
├── config.py                       # 统一配置加载
├── schemas.py                      # 共享数据模型（AgentAction, ToolResult 等）
│
├── runtime/                        # 运行时容器层
│   ├── session_runtime.py          # 顶层运行时：组装所有服务
│   ├── event_bus.py                # 事件总线（预留）
│   ├── event_types.py              # 事件类型定义
│   └── service_registry.py         # 服务注册表
│
├── sessions/                       # 会话管理
│   ├── schemas.py                  # SessionState, TurnState, QueryParam
│   ├── session_store.py            # 状态存储（内存版）
│   └── session_service.py          # 会话高层操作
│
├── engine/                         # 执行引擎
│   ├── query_engine.py             # Turn 生命周期（submit / resume_approval / resume_user_input）
│   ├── query_loop.py               # 单次 Turn 的 step-by-step 循环核心
│   ├── query_state.py              # QueryState / PendingAction 状态数据
│   ├── dispatcher.py               # 动作分发表（tool_call / plan / finish 等）
│   ├── transitions.py              # 状态转换：apply / sync / rebuild
│   ├── parser.py                   # LLM 输出 → AgentAction 解析
│   ├── planner.py                  # 任务规划与重规划
│   ├── verifier.py                 # 任务完成验证
│   └── prompt_service.py           # Prompt 构建服务
│
├── llm/                            # 大语言模型层
│   ├── base.py                     # LLM 客户端 Protocol 接口
│   ├── zhipu_client.py             # 智谱 GLM 实现
│   └── llm_service.py              # LLM 服务封装
│
├── tools/                          # 工具层
│   ├── base.py                     # BaseTool 抽象基类
│   ├── registry.py                 # 工具注册表
│   ├── tool_executor.py            # 工具执行器（Hook 拦截 + 审批 + 执行）
│   ├── file_tools.py               # 文件读写、目录列表
│   └── bash_tools.py               # Shell 命令
│
├── hooks/                          # Hook 拦截层
│   ├── pre_tool_use.py             # ToolInvocation, HookDecision, PreToolUseHook ABC
│   └── hook_manager.py             # HookManager（顺序链，首个非 allow 即短路）
│
├── policy/                         # 策略引擎
│   ├── policy_engine.py            # PolicyEngine（规则评估）+ PolicyHook（适配层）
│   └── policy_service.py           # PolicyService（兼容旧接口的薄包装）
│
├── approval/                       # 审批管理
│   ├── approval_store.py           # ApprovalRequest + ApprovalStore（内存存储）
│   ├── approval_service.py         # ApprovalService（创建 / 批准 / 拒绝请求）
│   └── cli_approval_adapter.py     # CLI 审批提示格式化
│
├── memory/                         # 记忆层
│   ├── memory_store.py             # 记忆存储
│   └── memory_service.py           # 记忆服务
│
├── context/                        # 上下文管理
│   ├── context_service.py          # 上下文构建
│   └── compactor.py                # 上下文裁剪
│
├── tracing/                        # 链路追踪
│   └── tracing_service.py          # 追踪服务（日志版）
│
├── prompts/                        # Prompt 模板
│   ├── action_prompt.py            # 动作决策 prompt（含 plan 进度 + 工具结果）
│   ├── planner_prompt.py           # 规划 prompt
│   ├── verify_prompt.py            # 验证 prompt
│   └── summary_prompt.py           # 总结 prompt
│
└── utils/                          # 工具函数
    ├── ids.py                      # ID 生成
    ├── json_utils.py               # JSON 提取与解析
    └── logging_utils.py            # 日志封装
```

---

## 核心数据流

一次用户输入触发的完整流程（以 write_file 需要审批为例）：

```
用户输入 "写一个程序到 /tmp/test.py"
        │
        ▼
   app.py (input loop)
        │
        ▼
   SessionRuntime.handle_user_input()
        │  判断：无 active turn → submit_message
        ▼
   QueryEngine.submit_message()
        │  1. 创建 TurnState
        │  2. 写入用户消息到 history + memory
        │  3. 可选：Planner 生成计划
        │  4. 构造 QueryState + QueryParam
        ▼
   query_loop(state, deps)          ← step-by-step 循环
        │
        │  每轮 step：
        │  ┌──────────────────────────────────────────┐
        │  │ ContextService.build_context()           │  从 session + turn 组装上下文
        │  │ PromptService.build_action_prompt()      │  构建 prompt（含 plan 进度）
        │  │ LLMService.generate()                    │  调用模型
        │  │ ActionParser.safe_parse()                │  解析为 AgentAction
        │  │                                          │
        │  │ dispatcher 分发：                         │
        │  │  tool_call → ToolExecutor.execute()      │
        │  │    ├ HookManager.run_pre_tool_use()      │  运行 Hook 链
        │  │    ├ PolicyHook → PolicyEngine.evaluate()│  策略检查
        │  │    ├ allow → 直接执行工具                 │
        │  │    ├ ask → 创建 ApprovalRequest，暂停    │
        │  │    └ deny → 返回拒绝结果                 │
        │  │  finish    → Verifier.verify()           │
        │  │  plan      → Planner.generate_plan()     │
        │  │  ask_user  → 暂停等待用户输入             │
        │  └──────────────────────────────────────────┘
        │
        ▼
   返回 waiting_user → app.py 等待用户审批
        │
        ▼
   用户输入 "y"
        │
        ▼
   SessionRuntime.handle_user_input()
        │  判断：active turn + waiting_user_approval → resume_approval
        ▼
   QueryEngine.resume_approval()
        │  1. rebuild_state_from_turn()
        │  2. parse_approval_response("y") → approved
        │  3. ApprovalService.approve(request_id)
        │  4. ToolExecutor.execute(..., approved=True)  ← 绕过 Hook
        │  5. 更新 plan step status → sync_state_to_turn
        │  6. 重新进入 query_loop()
        ▼
   query_loop 继续运行 → 下一步 / verify / finish
        │
        ▼
   QueryLoopResult → 返回给用户
```

---

## Hook 审批机制

Simple Agent 使用 Hook 链架构管理工具调用的安全性。核心设计是 **拦截层 + 审批服务** 的分离：

### 三层拦截

```
ToolExecutor.execute()
    │
    ├─ approved=True?  ──→  跳过所有拦截，直接执行
    │
    └─ approved=False:
         │
         ▼
       HookManager.run_pre_tool_use(invocation)
         │
         ├─ Hook 1: PolicyHook ──→ PolicyEngine.evaluate()
         │    ├ allow  → 放行，继续下一个 Hook
         │    ├ deny   → 短路，返回拒绝
         │    ├ ask    → 短路，需要人工审批
         │    └ context_required → 短路，需要上下文补充
         │
         └─ (未来可插入更多 Hook)
         │
         ▼
       全部 allow → 执行工具
```

### PolicyEngine 默认规则

| 工具 | 默认行为 | 可配置 |
|------|---------|--------|
| `read_file` | allow | `allow_read` |
| `list_dir` | allow | `allow_read` |
| `write_file` | ask（需要审批） | `allow_write` / `require_approval_for_write` |
| `bash` | ask（需要审批） | `allow_bash` / `require_approval_for_bash` |
| 其他工具 | allow | — |

危险命令（`rm -rf`、`mkfs`、`dd`、`format`）会被直接 deny。

### 审批流程状态机

```
                    ┌──────────┐
                    │ running  │
                    └────┬─────┘
                         │ tool_call 需要审批
                         ▼
                  ┌──────────────┐
         ┌───────│ waiting_user │───────┐
         │       │   _approval  │       │
         │       └──────────────┘       │
     用户批准                         用户拒绝
         │                               │
         ▼                               ▼
  resume_approval()               resume_approval()
  execute(approved=True)          记录拒绝结果
  更新 plan step                  mode → running
  mode → running                       │
         │                             │
         └─────────┬───────────────────┘
                   ▼
              query_loop 继续
```

### 扩展 Hook

要添加自定义拦截逻辑，只需实现 `PreToolUseHook`：

```python
from simple_agent.hooks.pre_tool_use import PreToolUseHook, ToolInvocation, HookDecision

class MyCustomHook(PreToolUseHook):
    async def before_tool_use(self, invocation: ToolInvocation) -> HookDecision:
        if invocation.tool_name == "bash" and "sudo" in invocation.args.get("command", ""):
            return HookDecision(status="deny", reason="sudo commands not allowed")
        return HookDecision(status="allow")
```

然后在 `SessionRuntime` 中注册：

```python
hook_manager = HookManager([PolicyHook(policy_engine), MyCustomHook()])
```

---

## 架构与运行模式

Simple Agent 采用分层组合架构，从顶层的运行时容器到底层的工具执行，每一层职责明确。

### SessionRuntime — 组合根

`SessionRuntime`（`runtime/session_runtime.py`）是整个系统的**组合根**。它在 `__init__` 中实例化并连接所有服务，确保上层代码无需关心依赖构造细节。

**组装顺序：**

```
MemoryStore → MemoryService → SessionSummaryService
    → SessionStore → SessionService
    → ContextService
    → PolicyEngine → PolicyHook → HookManager
    → ApprovalStore → ApprovalService
    → ToolRegistry (ReadFileTool, WriteFileTool, ListDirTool, BashTool) → ToolExecutor
    → ZhipuClient → LLMService
    → PromptService → ActionParser → Planner → Verifier → TracingService
    → QueryEngine
```

外部调用者（如 `app.py`）只需创建 `SessionRuntime(config)` 并调用 `start()`，即可使用所有功能。

**用户输入路由：** `handle_user_input(session_id, text)` 根据当前会话状态决定走哪条路径：

```python
async def handle_user_input(self, session_id: str, text: str) -> QueryLoopResult:
    session = self._session_store.get(session_id)
    if session.active_turn_id:
        turn = self._session_store.get_turn(session.active_turn_id)
        if turn.mode == "waiting_user_approval":
            return await self._query_engine.resume_approval(session_id, text)
        else:
            return await self._query_engine.resume_user_input(session_id, text)
    else:
        return await self._query_engine.submit_message(session_id, text)
```

### QueryEngine — 编排层

`QueryEngine`（`engine/query_engine.py`）管理 **Turn 的生命周期**，提供三个入口方法：

| 方法 | 触发条件 | 做什么 |
|------|---------|--------|
| `submit_message()` | 用户新输入 | 创建 TurnState → 记录消息到 history + memory → 可选生成计划 → 构造 QueryState + QueryParam → 进入 query_loop |
| `resume_approval()` | 用户审批回复 | 从 TurnState 重建状态 → 解析审批结果 → 执行被挂起的工具（`approved=True` 绕过 Hook）→ 更新计划步骤 → 重新进入 query_loop |
| `resume_user_input()` | 用户回答问题 | 从 TurnState 重建状态 → 记录用户回答 → 设 mode 为 running → 重新进入 query_loop |

`_build_deps()` 将所有服务打包为 `QueryParam` dataclass 传入 query_loop，实现无框架依赖注入。

### query_loop — 状态驱动的核心循环

`query_loop()`（`engine/query_loop.py`）是整个 Agent 的核心。它是一个 **状态机驱动的 while 循环**，每轮执行以下 11 步：

```
while not state.is_terminal():
    ① 终态检查：mode 为 completed/failed 则退出
    ② 挂起检查：mode 为 waiting_user_* 则 break，控制权还给调用者
    ③ 步数预算：step_count < max_steps 才继续
    ④ step_count += 1
    ⑤ 构建上下文：ContextService.build_context() → 8 个 PromptContext 块
    ⑥ 构建 Prompt：PromptService.build_action_prompt() → 7 层组装
    ⑦ 调用 LLM：LLMService.generate(prompt)
    ⑧ 解析动作：ActionParser.safe_parse()
        - 解析失败：parse_fail_count += 1，注入系统提示警告 LLM
        - 连续 3 次失败：转入 failed
    ⑨ 分发动作：dispatch_action() → 8 个 handler 之一
    ⑩ 状态转换：apply_transition() → 可能改变 mode
    ⑪ 持久化：sync_state_to_turn() → 写回 TurnState
```

**失败模式：**
- `max_steps` 超限（默认 20 步）
- LLM 调用异常（`llm_error`）
- 连续解析失败（`max_parse_fails`，默认 3 次）

### 信息流总览

```
用户输入
  └→ SessionRuntime.handle_user_input()
      └→ QueryEngine.submit_message()
          ├→ 创建 TurnState
          ├→ 记录消息到 history + memory
          ├→ 构造 QueryState + QueryParam
          └→ query_loop()
              ├→ ContextService.build_context()      ← 8 块上下文
              ├→ PromptService.build_action_prompt() ← 7 层 Prompt
              ├→ LLMService.generate()               ← 调用 LLM
              ├→ ActionParser.safe_parse()            ← JSON → AgentAction
              ├→ dispatch_action()                    ← 8 个 handler
              ├→ apply_transition()                   ← 状态转换
              └→ sync_state_to_turn()                 ← 持久化
```

### QueryState 模式与状态转换

`QueryState.mode` 有 5 种取值：

| Mode | 含义 | 如何进入 | 如何退出 |
|------|------|---------|---------|
| `running` | 主动执行中 | 初始状态，或 resume 后 | 任何 Transition 改变它 |
| `waiting_user_approval` | 挂起等待工具审批 | tool_call 需要 ask 审批 | `resume_approval()` |
| `waiting_user_input` | 挂起等待用户回答 | ask_user 动作 | `resume_user_input()` |
| `completed` | 任务完成 | finish 动作（验证通过） | 终态 |
| `failed` | 任务失败 | max_steps / llm_error / parse_fails | 终态 |

Transition 类型（`engine/transitions.py`）：

| Transition | 效果 |
|-----------|------|
| `continue` | mode 保持 running |
| `wait_user_input` | mode → waiting_user_input |
| `wait_user_approval` | mode → waiting_user_approval |
| `completed` | mode → completed |
| `failed` | mode → failed |

### 8 种动作类型

`dispatcher`（`engine/dispatcher.py`）支持 8 种 AgentAction：

| 动作类型 | Handler | 说明 |
|---------|---------|------|
| `tool_call` | `_handle_tool_call` | 执行单个工具：运行时防护 → Hook → 审批 → ToolExecutor |
| `tool_batch` | `_handle_tool_batch` | 并行执行多个只读工具（TaskScheduler DAG 调度） |
| `plan` | `_handle_plan` | 通过 Planner LLM 生成执行计划 |
| `replan` | `_handle_replan` | 步骤阻塞时重新规划 |
| `verify` | `_handle_verify` | 通过 Verifier LLM 检查任务是否完成 |
| `summarize` | `_handle_summarize` | 通过 LLM 生成进度摘要 |
| `ask_user` | `_handle_ask_user` | 暂停循环，向用户提问 |
| `finish` | `_handle_finish` | 验证完成（允许 2 次验证失败后强制完成） |

---

## 工具系统架构

工具系统位于 `simple_agent/tools/`，采用 **Core + 插件** 结构：`core/` 定义基类、注册表、执行器、防护和类型；每个具体工具独立目录，遵循四文件约定（`schemas.py`, `spec.py`, `tool.py`, `prompt.py`）。

### BaseTool 抽象基类

`tools/core/base.py` 定义了所有工具的接口：

```python
class BaseTool(ABC):
    spec: ToolSpec              # 声明式元数据（名称、描述、能力、保证）
    input_model: type[BaseModel]  # Pydantic 输入验证模型

    async def run(self, tool_input: BaseModel, ctx: dict | None = None) -> ToolObservation: ...

    async def validate(self, tool_input, ctx=None) -> ToolObservation | None:  # 可选
        return None

    async def check_preconditions(self, tool_input, ctx=None) -> ToolObservation | None:  # 可选
        return None
```

关键设计：**spec（声明式元数据）与 run（命令式逻辑）分离**。Prompt 系统通过 spec 生成工具描述，无需执行任何代码。

### ToolRegistry

`tools/core/registry.py` 提供简单的 name→instance 映射：

- `register(tool)` — 按名注册
- `default_registry()` — 工厂函数，注册 4 个内置工具
- `tool_descriptions_for_prompt()` — 从 spec 生成 Prompt 层的工具列表
- `list_specs()` — 返回可序列化的 spec 字典

### ToolExecutor 执行管道

`tools/core/executor.py` 的 `execute()` 方法按以下管道处理：

```
execute(tool_name, args, session_id, turn_id, approved=False)
  │
  ├─ ① ApprovalMemory 检查：本轮已批准则跳过 Hook
  │
  ├─ ② HookManager.run_pre_tool_use()（若未批准）
  │    ├ allow           → 继续
  │    ├ deny            → 返回错误 ToolResult
  │    ├ ask             → 创建 ApprovalRequest，返回 approval_required
  │    └ context_required → 返回需要上下文的 ToolObservation
  │
  ├─ ③ Registry 查找：tool_name → BaseTool 实例
  │
  ├─ ④ Pydantic 验证：tool.input_model(**args)
  │    └ 验证失败 → 返回错误 ToolResult
  │
  ├─ ⑤ 执行：await tool.run(input_model)
  │
  └─ ⑥ 异常包装：任何异常 → retryable=True 的错误 ToolObservation
```

### 运行时防护（Runtime Guards）

`tools/core/guards.py` 在 dispatcher 层（ToolExecutor 之前）检查：

**`check_write_without_evidence`**：阻止对同一文件的连续写入。如果上一步是成功的 `write_file` 到路径 P，且中间没有验证性操作（如 bash 测试失败、验证失败、新读取发现差异），则阻止当前 `write_file` 到路径 P。

**`check_read_after_write`**：阻止刚写入后立即读取。写入成功后，Agent 已知文件内容，再次读取是浪费。

两者返回 `status="context_required"` 的 ToolObservation，dispatcher 注入系统提示后继续循环。

### 四个内置工具

#### BashTool

| 属性 | 值 |
|------|-----|
| 文件 | `tools/bash/tool.py` |
| 输入 | `command: str`（必填），`timeout: int`（可选，1-300s，默认 30s） |
| 执行 | `asyncio.create_subprocess_shell()` + `asyncio.wait_for()` |
| 成功 | `ok=True`，data 含 command、exit_code、stdout、stderr |
| 失败 | `ok=False, retryable=True`，stderr 截断到 300 字符 |
| 能力 | `mutates_files=True, requires_approval=True, preferred_after_write=True` |

#### ReadFileTool

| 属性 | 值 |
|------|-----|
| 文件 | `tools/read_file/tool.py` |
| 输入 | `path: str`（必填），`start_line: int`（默认 1），`max_lines: int`（可选） |
| 执行 | UTF-8 读取，行切片，MD5 全文哈希 |
| 不变检测 | 通过 `ctx["read_cache"]` 比较哈希 → `status="unchanged"` |
| 输出 | data 含 content、total_lines、lines_read、truncated |
| 能力 | `read_only=True, idempotent=True, returns_high_value_payload=True` |

#### WriteFileTool

| 属性 | 值 |
|------|-----|
| 文件 | `tools/write_file/tool.py` |
| 输入 | `path: str`（必填），`content: str`（必填） |
| Noop 检测 | 读取旧内容，若 `old_content == content` 则返回 `status="noop"` |
| 执行 | `os.makedirs()` 创建父目录 → 全文覆写 |
| Diff 统计 | `difflib.unified_diff()` 计算 lines_added / lines_removed |
| 输出 | data 含 operation（created/updated）、lines_written、lines_added、lines_removed、changed_paths |
| 能力 | `mutates_files=True, requires_approval=True` |

> **注意：** 项目中没有独立的 EditTool，所有文件修改通过 WriteFileTool 全文覆写实现。

#### ListDirTool

| 属性 | 值 |
|------|-----|
| 文件 | `tools/list_dir/tool.py` |
| 输入 | `path: str`（必填） |
| 执行 | `os.listdir()` + 排序，facts 预览前 10 条 |
| 输出 | data 含完整 entries 列表 |
| 能力 | `read_only=True` |

### ToolObservation 结构

所有工具返回统一的 `ToolObservation`（`tools/core/types.py`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | `bool` | 工具是否执行成功 |
| `status` | `Literal` | 状态值（见下表） |
| `summary` | `str` | 一句话摘要 |
| `facts` | `list[str]` | 提取的事实，用于 Prompt 的 confirmed_facts |
| `data` | `dict` | 结构化结果数据（文件内容、exit_code 等） |
| `error` | `str \| None` | 错误信息 |
| `retryable` | `bool` | LLM 是否应考虑重试 |
| `changed_paths` | `list[str]` | 本次修改的文件路径 |

**Status 值含义：**

| Status | 含义 |
|--------|------|
| `success` | 正常成功 |
| `noop` | 写入内容与已有内容完全相同，未执行写入 |
| `unchanged` | 文件自上次读取后未变化 |
| `error` | 执行失败 |
| `approval_required` | 需要用户审批 |
| `context_required` | 防护拦截，缺少执行依据 |

---

## Prompt 构建机制

### 每步重建设计

Simple Agent 的 Prompt 系统**没有使用多轮对话历史**。每一步都从结构化状态重建完整的 Prompt。这意味着：

- LLM 每次收到的都是一个自包含的文本 Prompt
- 工具结果不作为对话消息对直接注入，而是通过上下文层（Layer F）间接呈现
- 状态管理在 QueryState / MemoryStore 中进行，而非依赖对话历史

### 七层组装

`assemble_prompt()`（`prompts/action_prompt.py`）将 7 层文本拼接为最终 Prompt：

```
┌──────────────────────────────────────────────────────────┐
│ Layer A: System Core        [静态] 工具协议               │
│ Layer B: Trust Rules        [静态] 结果信任规则           │
│ Layer C: Tool Contracts     [动态] 按注册工具生成         │
│ Layer D: Code Task Rules    [静态] 代码任务行为规则       │
│ Layer E: Capabilities       [动态] 工具描述 + 8 种动作    │
│ Layer F: Context            [动态] 8 块 PromptContext     │
│ User Input                  [动态] "User task: {message}" │
│                                                          │
│ Response (JSON only):                                    │
└──────────────────────────────────────────────────────────┘
```

| 层 | 函数 | 静态/动态 | 内容 |
|----|------|----------|------|
| A: System Core | `build_tool_protocol_prompt()` | 静态 | 工具协议：observation 结构、status 值、信任规则 |
| B: Trust Rules | `build_trust_rules_prompt()` | 静态 | 各工具的结果信任规则（如 "write 成功后不要 re-read"） |
| C: Tool Contracts | `build_tool_contracts_prompt(tools)` | 动态 | 从每个工具的 ToolSpec 生成：描述、用法、能力、保证 |
| D: Code Task Rules | `build_code_task_rules_prompt()` | 静态 | 代码任务行为规则：先读后写、prefer verify 等 |
| E: Capabilities | `build_capability_prompt(tool_descriptions)` | 动态 | 工具参数描述、8 种可用动作的 JSON 格式、Batch 并行读取说明 |
| F: Context | `build_context_prompt(prompt_context)` | 完全动态 | 8 块 PromptContext（见下节） |
| User Input | `f"User task: {state.user_message}"` | 动态 | 原始用户请求 |

**Layer A 示例（Tool Protocol）：**

```
Tool protocol:
1. Every tool call returns a structured observation with: ok, status, summary, facts, data, error.
2. Status values: success | noop | unchanged | error | approval_required | context_required.
3. If ok=true, the tool succeeded. Trust the result — do not re-verify.
...
```

**Layer C 示例（Tool Contracts，动态生成）：**

```
Tool contracts:
- read_file: Read file contents
  Usage: read_file(path, start_line, max_lines)
  Read-only: yes
  Guarantee: Returns file content as string
- write_file: Write content to file
  Requires approval: yes
  Guarantee: File content exactly matches input
...
```

### PromptContext 的 8 个字段

Layer F 的内容由 `ContextService.build_context()` 从 8 个数据源构建：

| 字段 | 构建方法 | 数据来源 | 用途 |
|------|---------|---------|------|
| `objective_block` | `_build_objective_block()` | state.user_message + current_plan | 当前目标、计划概要、交付物 |
| `execution_state` | `_build_execution_state()` | state.mode, step_count, plan 进度 | 执行进度、当前步骤、阻塞步骤 |
| `artifact_snapshot` | `_build_artifact_snapshot()` | ArtifactState | 文件快照（最多 2 文件 × 1500 字符）、写入保证、最新 Shell 结果 |
| `confirmed_facts` | `_build_confirmed_facts()` | MemoryService（最近 10 条，取成功工具的 facts） | 确认的事实（去重，最近 3 条工具结果） |
| `next_decision_point` | `_build_next_decision_point()` | 当前 plan 步骤 status + action_type | 下一步决策指引 |
| `compact_memory_summary` | `SessionSummaryService` | MemoryStore（最近 20 条非工具项） | 历史上下文摘要（去重、截断） |
| `working_set_summary` | `_build_working_set()` | session.working_set | 最近读/写文件、重复动作、read-after-write 警告 |
| `recent_observations` | `_build_recent_observations()` | MemoryService（最近 15 条） | 失败工具结果、最新验证结果 |

### 四个 Prompt 模板

系统有 4 个独立的 Prompt 模板，都由 `PromptService` 统一调用：

| 模板 | 函数 | 使用时机 | 特点 |
|------|------|---------|------|
| Action Prompt | `build_action_prompt()` | query_loop 每一步 | 完整 7 层组装，含上下文 |
| Planner Prompt | `build_planner_prompt()` | plan/replan 动作 | 聚焦生成结构化 ExecutionPlan JSON |
| Verify Prompt | `build_verify_prompt()` | verify/finish 动作 | 包含证据区段，返回 `{complete, reason, missing}` |
| Summary Prompt | `build_summary_prompt()` | summarize 动作 | 包含 compact_memory_summary，返回 `{summary, outputs, issues}` |

所有模板均以 `"Response (JSON only):"` 结尾，要求 LLM 返回单个 JSON 对象。

---

## 上下文与记忆管理

### MemoryStore — 底层存储

`memory/memory_store.py` 是一个内存字典，结构为 `dict[session_id, list[item]]`。

每个条目至少包含 `"role"` 字段，取值为：

| Role | 写入时机 | 内容 |
|------|---------|------|
| `user` | 用户输入时 | `{"role": "user", "content": text}` |
| `tool` | 工具执行后 | `{"role": "tool", "turn_id", "tool_name", "ok", "status", "summary", "facts", "data", "error", "changed_paths"}` |
| `system` | dispatcher 处理后 | `{"role": "system", "content": note}` — 记录工具执行摘要、计划更新、验证结果等 |

方法：`add(session_id, item)`、`get_recent(session_id, limit)`、`get_all(session_id)`。

### MemoryService — 记录服务

`memory/memory_service.py` 提供高层写入接口：

- **`record_user_message(session_id, text)`** — 存储 `{"role": "user", "content": text}`
- **`record_tool_result(session_id, turn_id, result)`** — 存储完整的工具结果字典（含 facts、data 等）
- **`add_system_note(session_id, note)`** — 存储系统备注（如 `"write_file(/tmp/test.py) -> ok"`）
- **`get_recent(session_id, limit)`** — 返回最近 N 条记忆

### SessionSummaryService — 紧凑摘要

`SessionSummaryService.get_compact_summary()` 的处理流程：

1. 从 MemoryService 获取最近 20 条记录
2. 过滤掉 `role=="tool"` 的条目（工具细节进入 confirmed_facts 和 recent_observations）
3. 按 `role:content[:100]` 去重，重复项标注 `(repeated Nx)`
4. 截断：user/system 条目 200 字符，tool 条目 80 字符
5. 格式化为 `[role] truncated_content`

### ContextService.build_context() — 上下文组装

`ContextService`（`context/context_service.py`）每次 step 调用 `build_context()`，从多个数据源组装 PromptContext 的 8 个字段：

```
build_context(session, turn, state)
  ├→ _build_objective_block(state)           ← state.user_message + current_plan
  ├→ _build_execution_state(session, state)  ← state.mode, step_count, plan steps
  ├→ _build_artifact_snapshot()              ← ArtifactState（内部维护）
  ├→ _build_confirmed_facts(session)         ← MemoryService（最近成功工具的 facts）
  ├→ _build_next_decision_point(state)       ← 当前 plan 步骤 status + action_type
  ├→ get_compact_summary(session_id)         ← SessionSummaryService
  ├→ _build_working_set(session)             ← session.working_set
  └→ _build_recent_observations(session)     ← MemoryService（失败工具 + 验证结果）
```

### ArtifactState — 文件与 Shell 状态

`context/artifact_state.py` 维护三个核心数据结构：

- **`files: dict[str, FileArtifact]`** — 每文件状态：snapshot 内容、stale 标记、最后写入信息、最后更新步数
- **`shell_results: list[ShellArtifact]`** — Shell 执行结果：command、exit_code、stdout、stderr
- **`write_guarantees: list[dict]`** — 写入保证记录

**预算限制：**
- `project_snapshots(budget=2, max_chars=1500)` — 最多投影 2 个文件快照，每个截断到 1500 字符
- `project_latest_shell(max_stdout=1000, max_stderr=800)` — 只保留最新的 Shell 结果
- `project_write_guarantees()` — 最近 3 条保证

**关键行为：** 文件写入后，其读取快照标记为 `stale=True` 并清除，确保 Agent 不会看到过期内容。

### WorkingSet — 文件追踪

`context/context_layers.py` 中的 `WorkingSet` 追踪文件访问模式：

- `recently_read_files` / `recently_written_files` — 列表，`summarize()` 展示最近 10 条
- `_action_counts` — 按 `{tool}:{sorted_args}` 统计频率，检测重复动作
- `repeated_actions` — 返回 count ≥ 2 的动作
- 用于运行时防护（read-after-write 检测）和上下文（working_set_summary 块）

### 上下文压缩策略

系统通过 5 种机制控制 Prompt 大小：

| 策略 | 机制 | 效果 |
|------|------|------|
| **快照预算** | 最多 2 个文件，每个 1500 字符 | 文件内容不无限增长 |
| **Shell 截断** | stdout ≤ 1000 字符，stderr ≤ 800 字符 | 命令输出有界 |
| **事实提取** | 最近 3 条成功工具的 facts，去重 | 只保留关键信息 |
| **记忆去重** | 按 `role:content[:100]` 去重，标注重复次数 | 减少冗余 |
| **无状态重建** | 每步从结构化状态重建完整 Prompt | 大小由预算参数决定，不随对话增长 |

### 双历史系统

系统维护两套独立的历史记录：

| 历史 | 位置 | 用途 | 是否用于 Prompt |
|------|------|------|----------------|
| `SessionState.message_history` | `sessions/schemas.py` | 外部检查/调试 | **否** |
| `MemoryStore` | `memory/memory_store.py` | Prompt 构建的主要数据源 | **是** |

`SessionState.message_history` 由 `SessionService.append_message()` 维护，只追加用户消息，不参与 Prompt 组装。`MemoryStore` 存储所有角色（user/tool/system）的完整记录，是 ContextService 构建上下文时的唯一数据源。

---

## 模块详解

### `sessions/` — 会话管理

管理用户会话的生命周期。一个 Session 代表一次持续对话，包含多条消息历史；一个 Turn 代表一次用户输入触发的完整处理过程。

| 类 | 职责 |
|----|------|
| `SessionState` | 会话状态：ID、消息历史、当前计划、工作目录 |
| `TurnState` | 单次 Turn 状态：ID、步数、当前动作、验证结果、审批挂起动作 |
| `SessionStore` | 内存存储：Session 和 Turn 的 CRUD，是系统状态真源 |
| `SessionService` | 高层操作：创建会话、追加消息、标记状态 |
| `QueryParam` | query_loop 的参数打包，包含所有依赖注入 |

### `engine/` — 执行引擎

Agent 智能行为的核心。**QueryEngine** 和 **query_loop** 的分离是最关键的架构设计：

- **QueryEngine**：Turn 生命周期管理，提供三个入口方法：
  - `submit_message()` — 新建 Turn，执行任务
  - `resume_approval()` — 恢复审批挂起的 Turn，执行批准/拒绝后继续
  - `resume_user_input()` — 恢复用户输入挂起的 Turn
- **query_loop**：单次 Turn 内的 step-by-step 推进循环，是 Agentic Loop 的本体

> 详细的运行模式、query_loop 执行流程、状态转换和 8 种动作类型见 [架构与运行模式](#架构与运行模式) 章节。

| 类/函数 | 职责 |
|---------|------|
| `QueryEngine` | Turn 生命周期：submit / resume_approval / resume_user_input |
| `query_loop()` | 每轮 step：构建上下文 → 调 LLM → 解析动作 → 分发处理 → 循环或退出 |
| `QueryState` | 循环内状态：mode、step_count、last_tool_result、current_plan 等 |
| `dispatcher` | 动作分发表：支持 8 种动作类型（tool_call / tool_batch / plan / replan / verify / summarize / ask_user / finish） |
| `transitions` | 状态转换函数：apply_transition、sync_state_to_turn、rebuild_state_from_turn |
| `ActionParser` | 将 LLM 的 JSON 输出解析为 `AgentAction`（tool_call / finish / replan / ask_user） |
| `Planner` | 判断是否需要规划、生成计划、重规划 |
| `Verifier` | 任务完成后验证是否真正达成目标 |
| `PromptService` | 统一构建各类 Prompt，包含 plan 进度格式化和工具结果格式化 |

### `hooks/` — Hook 拦截层

在工具执行前插入可扩展的拦截链，是安全策略的核心抽象层。

| 类/函数 | 职责 |
|---------|------|
| `ToolInvocation` | 工具调用描述：session_id、turn_id、tool_name、args |
| `HookDecision` | Hook 决策：status (allow/deny/ask/context_required) + reason + message |
| `PreToolUseHook` | Hook 抽象基类，实现 `before_tool_use(invocation) -> HookDecision` |
| `HookManager` | 管理 Hook 链，顺序执行，首个非 allow 决策短路返回 |

### `policy/` — 策略引擎

基于可配置规则的工具调用策略。

| 类 | 职责 |
|----|------|
| `PolicyEngine` | 规则评估引擎：根据工具名和配置规则返回 allow/deny/ask |
| `PolicyHook` | `PreToolUseHook` 适配器：将 PolicyEngine 包装为 Hook 链的一环 |
| `PolicyService` | 兼容旧接口的薄包装，内部委托给 PolicyEngine |

### `approval/` — 审批管理

管理需要人工审批的工具调用请求的生命周期。

| 类 | 职责 |
|----|------|
| `ApprovalRequest` | 审批请求数据：request_id、tool_name、args、status (pending/approved/denied) |
| `ApprovalStore` | 内存存储：按 request_id 存取审批请求 |
| `ApprovalService` | 审批服务：创建请求、批准、拒绝、查询 |
| `CLIApprovalAdapter` | CLI 格式化：将审批请求格式化为用户可读的提示文本 |

### `llm/` — 大语言模型

通过 Protocol 接口抽象模型调用，支持替换底层实现。

| 类 | 职责 |
|----|------|
| `BaseLLMClient` | Protocol 接口：`complete()`、`stream()`、`complete_with_messages()` |
| `ZhipuClient` | 智谱 GLM 实现：含重试、超时处理 |
| `LLMService` | 服务包装：统一入口、日志记录、错误处理 |

如需接入其他模型（如 OpenAI），只需实现 `BaseLLMClient` Protocol，无需改动上层代码。

### `tools/` — 工具系统

Agent 可调用的能力单元。每个工具继承 `BaseTool`，实现 `async run(**kwargs) -> str`。

> 详细的工具架构、执行管道、运行时防护和 ToolObservation 结构见 [工具系统架构](#工具系统架构) 章节。

| 类 | 职责 |
|----|------|
| `BaseTool` | 抽象基类：定义 spec、input_model、run() |
| `ToolRegistry` | 工具注册表：按名查找、列出工具描述 |
| `ToolExecutor` | 工具执行器：Hook 拦截 → 审批 → Pydantic 验证 → 执行 → 返回结构化结果 |
| `ReadFileTool` | 读取文件内容（支持行切片、不变检测） |
| `WriteFileTool` | 写入文件（自动创建父目录、Noop 检测、Diff 统计） |
| `ListDirTool` | 列出目录内容 |
| `BashTool` | 执行 Shell 命令（asyncio subprocess，超时 1-300s，默认 30s） |

**添加新工具**只需：1) 继承 `BaseTool`，2) 在 `SessionRuntime` 中注册。

### `memory/` — 记忆系统

为 Agent 提供跨 step 的上下文记忆，以 session 为单位存储。

> 详细的记忆管理架构见 [上下文与记忆管理](#上下文与记忆管理) 章节。

| 类 | 职责 |
|----|------|
| `MemoryStore` | 底层存储：按 session_id 存储记忆条目列表 |
| `MemoryService` | 高层服务：记录用户消息、工具结果、系统备注 |
| `SessionSummaryService` | 紧凑摘要：从 MemoryService 提取最近 20 条非工具记录，去重、截断后生成摘要 |

### `context/` — 上下文管理

控制每次 LLM 调用时注入的上下文窗口大小。

> 详细的上下文构建流程、ArtifactState 和压缩策略见 [上下文与记忆管理](#上下文与记忆管理) 章节。

| 类 | 职责 |
|----|------|
| `ContextService` | 从 session 和 turn 组装 PromptContext 的 8 个字段 |
| `ContextCompactor` | 裁剪过长历史和工具输出（当前为简单截断） |
| `ArtifactState` | 维护文件快照、Shell 结果、写入保证（预算控制） |
| `WorkingSet` | 追踪最近读/写文件、检测重复动作和 read-after-write |

### `tracing/` — 链路追踪

| 类 | 职责 |
|----|------|
| `TracingService` | 轻量追踪：span 开始/结束、事件记录（当前输出到日志） |

### `prompts/` — Prompt 模板

四个独立的 prompt 构建函数，由 `PromptService` 统一调用：

| 函数 | 用途 |
|------|------|
| `build_action_prompt()` | 每轮 step 的动作决策 prompt（含 plan 进度、工具结果、防重复规则） |
| `build_planner_prompt()` / `build_replan_prompt()` | 规划 / 重规划 prompt |
| `build_verify_prompt()` | 任务完成验证 prompt |
| `build_summary_prompt()` | 最终总结 prompt |

### `schemas.py` — 共享数据模型

使用 Pydantic BaseModel 定义的全局共享数据结构：

| 模型 | 用途 |
|------|------|
| `AgentAction` | LLM 决策的动作（type, tool, args, message） |
| `ToolResult` | 工具执行结果（success, output, error, approval_required, approval_request_id） |
| `PolicyDecision` | 策略检查结果 |
| `TaskPlan` / `PlanStep` | 任务计划与步骤 |

---

## 配置参考

### `configs/model.yaml`

```yaml
provider: zhipu
model_name: glm-4.7
temperature: 0.0
max_tokens: 4096
timeout: 60
```

### `configs/agent.yaml`

```yaml
max_steps: 20
enable_planning: true
planning_threshold: 2
memory_window: 10
```

### `configs/policy.yaml`

```yaml
allow_read: true
allow_write: false
allow_bash: false
require_approval_for_write: true
require_approval_for_bash: true
blocked_commands:
  - rm -rf
  - mkfs
  - dd
  - format
```
