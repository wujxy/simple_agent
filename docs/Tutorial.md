# Simple Agent 教程

## 项目简介

Simple Agent 是一个基于 LLM 的自主代理框架，能够理解用户意图、制定计划、调用工具执行任务，并自动验证结果。

核心特性：

- **常驻会话**：程序启动后持续运行，支持多轮对话
- **自主规划**：复杂任务自动拆解为多步计划，支持重规划
- **工具调用**：内置文件读写、目录列表、Shell 命令等工具
- **权限控制**：写操作和 Shell 命令需经过策略审批
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

> 列出当前目录的文件

Step 1/1
[INFO] query_loop: Step 1/1
...
Agent finished: 当前目录包含以下文件：...

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
│   ├── query_engine.py             # Turn 生命周期管理（不包含循环逻辑）
│   ├── query_loop.py               # 单次 Turn 的 step-by-step 循环核心
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
│   ├── tool_executor.py            # 工具执行器（含策略检查）
│   ├── file_tools.py               # 文件读写、目录列表
│   └── bash_tools.py               # Shell 命令
│
├── memory/                         # 记忆层
│   ├── memory_store.py             # 记忆存储
│   └── memory_service.py           # 记忆服务
│
├── context/                        # 上下文管理
│   ├── context_service.py          # 上下文构建
│   └── compactor.py                # 上下文裁剪
│
├── policy/                         # 权限控制
│   └── policy_service.py           # 策略服务
│
├── tracing/                        # 链路追踪
│   └── tracing_service.py          # 追踪服务（日志版）
│
├── prompts/                        # Prompt 模板
│   ├── action_prompt.py            # 动作决策 prompt
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

一次用户输入触发的完整流程：

```
用户输入 "读取 config.py"
        │
        ▼
   app.py (input loop)
        │
        ▼
   SessionRuntime.handle_user_input()
        │
        ▼
   QueryEngine.submit_message()
        │  1. 创建 TurnState
        │  2. 写入用户消息到 history + memory
        │  3. 可选：Planner 生成计划
        │  4. 构造 QueryParam
        ▼
   query_loop(param)          ← 单次 Turn 的 step-by-step 循环
        │
        │  每轮 step：
        │  ┌─────────────────────────────────┐
        │  │ ContextService.build_context()  │  组装上下文
        │  │ PromptService.build_prompt()    │  构建 prompt
        │  │ LLMService.generate()           │  调用模型
        │  │ ActionParser.parse()            │  解析动作
        │  │                                 │
        │  │ 分支处理：                        │
        │  │  tool_call → ToolExecutor       │  registry → policy → run
        │  │  finish    → Verifier.verify()  │  验证后返回
        │  │  replan    → Planner.replan()   │  重规划后继续
        │  │  ask_user  → 返回等待用户        │
        │  └─────────────────────────────────┘
        │
        ▼
   QueryLoopResult → 返回给用户
```

---

## 模块详解

### `sessions/` — 会话管理

管理用户会话的生命周期。一个 Session 代表一次持续对话，包含多条消息历史；一个 Turn 代表一次用户输入触发的完整处理过程。

| 类 | 职责 |
|----|------|
| `SessionState` | 会话状态：ID、消息历史、当前计划、工作目录 |
| `TurnState` | 单次 Turn 状态：ID、步数、当前动作、验证结果 |
| `SessionStore` | 内存存储：Session 和 Turn 的 CRUD，是系统状态真源 |
| `SessionService` | 高层操作：创建会话、追加消息、标记状态 |
| `QueryParam` | query_loop 的参数打包，包含所有依赖注入 |

### `engine/` — 执行引擎

Agent 智能行为的核心。**QueryEngine** 和 **query_loop** 的分离是最关键的架构设计：

- **QueryEngine**：只做 Turn 生命周期管理（创建 turn、写消息、调用 loop、收尾），不包含循环逻辑
- **query_loop**：单次 Turn 内的 step-by-step 推进循环，是 Agentic Loop 的本体

| 类/函数 | 职责 |
|---------|------|
| `QueryEngine` | Turn 生命周期：创建 turn → 调用 query_loop → 返回结果 |
| `query_loop()` | 每轮 step：构建上下文 → 调 LLM → 解析动作 → 分支处理 → 循环或退出 |
| `ActionParser` | 将 LLM 的 JSON 输出解析为 `AgentAction`（tool_call / finish / replan / ask_user） |
| `Planner` | 判断是否需要规划、生成计划、重规划 |
| `Verifier` | 任务完成后验证是否真正达成目标 |
| `PromptService` | 统一构建各类 Prompt，封装模板调用 |

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

| 类 | 职责 |
|----|------|
| `BaseTool` | 抽象基类：定义 name、description、args_schema、run() |
| `ToolRegistry` | 工具注册表：按名查找、列出工具描述 |
| `ToolExecutor` | 工具执行器：策略检查 → 查找工具 → 执行 → 返回结构化结果 |
| `ReadFileTool` | 读取文件内容 |
| `WriteFileTool` | 写入文件（自动创建父目录） |
| `ListDirTool` | 列出目录内容 |
| `BashTool` | 执行 Shell 命令（asyncio subprocess，30s 超时） |

**添加新工具**只需：1) 继承 `BaseTool`，2) 在 `SessionRuntime` 中注册。

### `memory/` — 记忆系统

为 Agent 提供跨 step 的上下文记忆，以 session 为单位存储。

| 类 | 职责 |
|----|------|
| `MemoryStore` | 底层存储：按 session_id 存储记忆条目列表 |
| `MemoryService` | 高层服务：记录用户消息、工具结果、系统备注 |

### `context/` — 上下文管理

控制每次 LLM 调用时注入的上下文窗口大小。

| 类 | 职责 |
|----|------|
| `ContextService` | 从 session 和 memory 组装上下文字典 |
| `ContextCompactor` | 裁剪过长历史和工具输出（当前为简单截断） |

### `policy/` — 权限控制

基于规则的工具调用审批。

| 类 | 职责 |
|----|------|
| `PolicyService` | 检查工具调用权限，返回 allow / ask / deny |

默认规则：
- `read_file` / `list_dir` → allow
- `write_file` → ask（需要审批）
- `bash` → ask（需要审批）
- 包含 `rm -rf`、`mkfs` 等的命令 → deny

### `runtime/` — 运行时容器

系统顶层组装和运行管理。

| 类 | 职责 |
|----|------|
| `SessionRuntime` | 顶层容器：创建并组装所有服务，提供 `create_session()` 和 `handle_user_input()` |
| `EventBus` | 事件分发：subscribe / publish（第一版为日志占位） |
| `ServiceRegistry` | 服务注册表：按名查找服务实例 |

### `tracing/` — 链路追踪

| 类 | 职责 |
|----|------|
| `TracingService` | 轻量追踪：span 开始/结束、事件记录（当前输出到日志） |

### `prompts/` — Prompt 模板

四个独立的 prompt 构建函数，由 `PromptService` 统一调用：

| 函数 | 用途 |
|------|------|
| `build_action_prompt()` | 每轮 step 的动作决策 prompt |
| `build_planner_prompt()` / `build_replan_prompt()` | 规划 / 重规划 prompt |
| `build_verify_prompt()` | 任务完成验证 prompt |
| `build_summary_prompt()` | 最终总结 prompt |

### `schemas.py` — 共享数据模型

使用 Pydantic BaseModel 定义的全局共享数据结构：

| 模型 | 用途 |
|------|------|
| `AgentAction` | LLM 决策的动作（type, tool, args, message） |
| `ToolResult` | 工具执行结果（success, output, error） |
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
