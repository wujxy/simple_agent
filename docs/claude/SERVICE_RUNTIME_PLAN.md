# SERVICE_RUNTIME_PLAN.md

# simple_agent 服务化运行时重构方案

> 目标：将当前 `simple_agent` 从“单文件/单类中的 step-by-step agent loop”重构为“会话常驻 + 服务化 + QueryEngine / query_loop 分层”的运行时架构。  
> 本文档面向执行者（如 Claude Code），要求按文件逐步实现，不要自由发挥出额外复杂子系统。

---

# 1. 总体目标

将当前系统重构为如下形态：

- 程序常驻，不再是一条命令执行完就退出的单任务脚本
- 引入 Session Runtime，持续接收用户输入
- 将 QueryEngine 从主循环中拆出，作为“会话/turn 封装器”
- 将真正的 agentic loop 下沉到 `query_loop.py`
- 将工具执行独立为 `ToolExecutor`
- 将模型调用独立为 `LLMService`
- 将记忆与推理上下文拆为 `MemoryService` / `ContextService`
- 将权限控制独立为 `PolicyService`
- 为未来的 tracing / hooks / approvals / streaming 留出接口

---

# 2. 设计原则

## 2.1 QueryEngine 不实现 while-loop 的业务细节
`QueryEngine` 只负责：
- 接收用户消息
- 创建 turn
- 组装调用参数
- 调用 `query_loop(...)`
- 处理 query 完成后的收尾

禁止在 `QueryEngine` 中直接实现：
- prompt 拼接细节
- 工具执行
- memory 写入底层逻辑
- context compaction
- permission 判定
- 长 while-loop 业务分支

## 2.2 query_loop 是一次 turn 的执行内核
`query_loop.py` 承担真正的一次 query 内部循环：

- build context
- build prompt
- call llm
- parse action
- run tool
- save result
- verify / finish / continue / replan

它只作用于“当前 turn”，不作用于整个程序生命周期。

## 2.3 服务之间通过清晰接口协作
允许直接通过依赖注入调用服务方法。  
EventBus 可先实现基础版，不强制所有逻辑一开始都靠事件驱动，但所有服务要预留接入事件的能力。

## 2.4 SessionStore 是状态真源
所有持久状态以 `SessionStore` 为准。  
各服务不要长期持有自己的状态副本，避免状态分裂。

## 2.5 先做单进程单事件循环
不要在第一版实现：
- 多进程 worker
- 真正分布式服务
- 网络服务化
- 向量数据库
- 多 agent 编排

本方案是**单进程服务化运行时**，不是微服务系统。

---

# 3. 目标目录结构

```text
simple_agent/
├── app.py
├── config.py
├── runtime/
│   ├── __init__.py
│   ├── session_runtime.py
│   ├── event_bus.py
│   ├── event_types.py
│   └── service_registry.py
├── sessions/
│   ├── __init__.py
│   ├── session_service.py
│   ├── session_store.py
│   └── schemas.py
├── engine/
│   ├── __init__.py
│   ├── query_engine.py
│   ├── query_loop.py
│   ├── parser.py
│   ├── planner.py
│   ├── verifier.py
│   └── prompt_service.py
├── llm/
│   ├── __init__.py
│   ├── llm_service.py
│   ├── base.py
│   └── zhipu_client.py
├── tools/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── tool_executor.py
│   ├── file_tools.py
│   └── bash_tools.py
├── memory/
│   ├── __init__.py
│   ├── memory_service.py
│   └── memory_store.py
├── context/
│   ├── __init__.py
│   ├── context_service.py
│   └── compactor.py
├── policy/
│   ├── __init__.py
│   └── policy_service.py
├── tracing/
│   ├── __init__.py
│   └── tracing_service.py
└── utils/
    ├── __init__.py
    ├── ids.py
    ├── json_utils.py
    └── logging_utils.py
```

---

# 4. 关键数据结构要求

建议使用 `dataclasses` 或 `pydantic`。优先保持简单。

## 4.1 `sessions/schemas.py`

### `SessionState`
```python
@dataclass
class SessionState:
    session_id: str
    created_at: float
    status: str                      # active / waiting_user / failed / closed
    cwd: str | None
    message_history: list[dict]
    current_plan: dict | None
    active_turn_id: str | None
    permission_state: dict
    context_meta: dict
    memory_meta: dict
```

### `TurnState`
```python
@dataclass
class TurnState:
    turn_id: str
    session_id: str
    user_message: str
    status: str                      # running / waiting_tool / waiting_user / completed / failed
    step_count: int
    max_steps: int
    current_action: dict | None
    last_tool_result: dict | None
    verification_result: dict | None
    started_at: float
    finished_at: float | None
```

### `AgentAction`
```python
@dataclass
class AgentAction:
    type: str                        # tool_call / ask_user / finish / replan
    reason: str
    tool: str | None = None
    args: dict | None = None
    message: str | None = None
```

### `ToolResult`
```python
@dataclass
class ToolResult:
    success: bool
    tool_name: str
    args: dict
    output: str | None = None
    error: str | None = None
    metadata: dict | None = None
```

### `QueryLoopResult`
```python
@dataclass
class QueryLoopResult:
    status: str                      # completed / waiting_user / failed
    message: str
    final_action: dict | None = None
```

---

# 5. 各文件逐个实现规范

## 5.1 `app.py`

### 目的
程序入口。  
负责启动 `SessionRuntime`，进入输入循环。

### 必须实现
#### `async def main() -> None`
输入：
- 无

输出：
- 无

职责：
- 加载配置
- 创建 `SessionRuntime`
- 调用 `runtime.start()`
- 创建或恢复默认 session
- 持续读取用户输入
- 将输入交给 `runtime.handle_user_input(...)`
- 将结果打印到终端

### 依赖
- `config.py`
- `runtime/session_runtime.py`

### 禁止
- 不要在这里写 agent loop
- 不要直接调模型
- 不要直接执行业务工具

---

## 5.2 `config.py`

### 目的
加载配置并组织为简单对象。

### 必须实现
#### `def load_config() -> dict`
输入：
- 可选环境变量 / 默认配置文件路径

输出：
- dict 配置对象

建议包含：
- runtime.max_steps
- model.provider
- model.name
- model.temperature
- policy.allow_write
- policy.allow_bash
- context.recent_history_limit
- context.max_prompt_chars

### 依赖
- 标准库即可

---

## 5.3 `runtime/session_runtime.py`

### 目的
系统顶层运行时容器。

### 必须实现
#### `class SessionRuntime`

### `__init__(self, config: dict)`
输入：
- 配置对象

输出：
- 无

职责：
- 初始化 EventBus
- 初始化 SessionStore
- 初始化全部服务
- 注册服务到 ServiceRegistry

### `async def start(self) -> None`
职责：
- 启动需要初始化的服务
- 进行必要的 runtime 级日志记录

### `async def stop(self) -> None`
职责：
- 做清理和关闭

### `async def create_session(self, cwd: str | None = None) -> str`
输出：
- 新 session_id

职责：
- 调用 SessionService 创建 session

### `async def handle_user_input(self, session_id: str, text: str) -> QueryLoopResult`
职责：
- 校验 session 是否存在
- 调用 `QueryEngine.submit_message(...)`
- 返回 query loop 结果

### 依赖
- `runtime/event_bus.py`
- `runtime/service_registry.py`
- `sessions/session_service.py`
- `sessions/session_store.py`
- `engine/query_engine.py`
- `llm/llm_service.py`
- `tools/tool_executor.py`
- `memory/memory_service.py`
- `context/context_service.py`
- `policy/policy_service.py`
- `tracing/tracing_service.py`

### 禁止
- 不要自己写 query loop
- 不要自己拼 prompt
- 不要直接执行工具

---

## 5.4 `runtime/event_types.py`

### 目的
定义基础事件结构。

### 必须实现
#### `@dataclass class Event`
字段：
- event_id: str
- session_id: str
- turn_id: str | None
- type: str
- source: str
- payload: dict
- ts: float

### 可选
定义常量：
- USER_MESSAGE_RECEIVED
- TURN_STARTED
- TOOL_REQUESTED
- TOOL_COMPLETED
- LLM_REQUEST_STARTED
- LLM_RESPONSE_COMPLETED
- VERIFICATION_COMPLETED

---

## 5.5 `runtime/event_bus.py`

### 目的
事件分发器。

### 必须实现
#### `class EventBus`

### `def subscribe(self, event_type: str, handler: Callable) -> None`
职责：
- 订阅事件

### `async def publish(self, event: Event) -> None`
职责：
- 逐个调用订阅者
- 保持简单，不做复杂中间件

### 依赖
- `runtime/event_types.py`

### 备注
第一版可非常简单。  
不需要复杂优先级、重试、持久化队列。

---

## 5.6 `runtime/service_registry.py`

### 目的
集中保存服务实例，方便调试和注入。

### 必须实现
#### `class ServiceRegistry`

### `def register(self, name: str, service: object) -> None`
### `def get(self, name: str) -> object`

---

## 5.7 `sessions/session_store.py`

### 目的
状态真源。

### 必须实现
#### `class SessionStore`

### `def create_session(self, cwd: str | None = None) -> SessionState`
### `def get_session(self, session_id: str) -> SessionState`
### `def save_session(self, session: SessionState) -> None`
### `def create_turn(self, session_id: str, user_message: str, max_steps: int) -> TurnState`
### `def get_turn(self, session_id: str, turn_id: str) -> TurnState`
### `def save_turn(self, turn: TurnState) -> None`

### 状态要求
- 内存版即可
- session_id -> SessionState
- turn_id -> TurnState

### 禁止
- 不要掺杂业务逻辑
- 不要做 prompt 相关操作

---

## 5.8 `sessions/session_service.py`

### 目的
对 `SessionStore` 做更高层包装。

### 必须实现
#### `class SessionService`

### `def __init__(self, store: SessionStore, event_bus: EventBus)`
### `async def create_session(self, cwd: str | None = None) -> SessionState`
### `async def get_session(self, session_id: str) -> SessionState`
### `async def append_message(self, session_id: str, role: str, content: str) -> None`
### `async def mark_waiting_user(self, session_id: str, turn_id: str, message: str) -> None`
### `async def close_turn(self, session_id: str, turn_id: str, status: str) -> None`

### 依赖
- `sessions/session_store.py`
- `runtime/event_bus.py`

---

## 5.9 `engine/query_engine.py`

### 目的
会话级 query 封装器。  
**它不是 query loop 本体。**

### 必须实现
#### `class QueryEngine`

### `__init__(...)`
必须注入：
- session_store
- session_service
- memory_service
- context_service
- prompt_service
- llm_service
- tool_executor
- planner
- verifier
- parser
- tracing_service
- config

### `async def submit_message(self, session_id: str, user_text: str) -> QueryLoopResult`
职责：
1. 读取 SessionState
2. 创建 TurnState
3. 将用户输入写入 session history
4. 将用户输入写入 memory
5. 调用 `query_loop(...)`
6. 根据返回结果更新 turn/session 状态
7. 返回结果给 runtime

### 输入
- session_id: str
- user_text: str

### 输出
- `QueryLoopResult`

### 禁止
- 不要在这里实现 while-loop
- 不要直接跑工具
- 不要直接调模型多轮推进

---

## 5.10 `engine/query_loop.py`

### 目的
真正的一次 turn 执行循环。

### 必须实现
#### `async def query_loop(...) -> QueryLoopResult`

建议签名：
```python
async def query_loop(
    session: SessionState,
    turn: TurnState,
    session_store: SessionStore,
    session_service: SessionService,
    memory_service: MemoryService,
    context_service: ContextService,
    prompt_service: PromptService,
    llm_service: LLMService,
    tool_executor: ToolExecutor,
    planner: Planner,
    verifier: Verifier,
    parser: ActionParser,
    tracing_service: TracingService,
) -> QueryLoopResult:
    ...
```

### 职责
循环直到：
- finish 并验证通过
- ask_user
- max_steps exceeded
- unrecoverable failure

### 每轮 step 必须做的事
1. `ContextService.build_context(...)`
2. `PromptService.build_action_prompt(...)`
3. `LLMService.generate(...)`
4. `ActionParser.parse_action(...)`
5. 根据 action 分支：
   - finish
   - ask_user
   - replan
   - tool_call
6. 如果 tool_call：
   - `ToolExecutor.execute(...)`
   - `MemoryService.record_tool_result(...)`
   - 更新 turn 状态
7. 发布必要 tracing/event

### finish 逻辑
- 必须调用 `Verifier.verify(...)`
- 只有 verify 通过才真正完成
- verify 不通过则写入 system note 并继续 loop

### ask_user 逻辑
- 返回 `QueryLoopResult(status="waiting_user", ...)`

### replan 逻辑
- 调用 `Planner.replan(...)`
- 然后继续 loop

### max_steps
- 到达上限返回失败结果

### 禁止
- 不要在里面直接实现具体工具逻辑
- 不要直接操作原始 provider API
- 不要自行决定权限策略

---

## 5.11 `engine/parser.py`

### 目的
解析模型输出为结构化 action。

### 必须实现
#### `class ActionParser`

### `def parse_action(self, llm_text: str) -> AgentAction`
职责：
- 提取 JSON
- 校验字段
- 返回 `AgentAction`

### 错误处理
- 解析失败时抛出明确异常
- 不要静默容错成奇怪结果

### 依赖
- `sessions/schemas.py`
- `utils/json_utils.py`

---

## 5.12 `engine/planner.py`

### 目的
计划与重规划。

### 必须实现
#### `class Planner`

### `async def maybe_plan(self, session: SessionState, turn: TurnState) -> dict | None`
职责：
- 判断是否需要 planning
- 返回 plan 或 None

### `async def replan(self, session: SessionState, turn: TurnState) -> dict`
职责：
- 基于当前上下文重规划
- 更新 `session.current_plan`

### 备注
第一版可轻量实现。
不要做过度复杂的 planner。

---

## 5.13 `engine/verifier.py`

### 目的
验证任务是否真的完成。

### 必须实现
#### `class Verifier`

### `async def verify(self, session: SessionState, turn: TurnState) -> dict`
返回示例：
```python
{
    "complete": True,
    "missing": []
}
```

或

```python
{
    "complete": False,
    "missing": ["Did not verify file contents after write"]
}
```

### 职责
- 对 finish 前结果做最终检查
- 先做轻量逻辑检查
- 必要时可调用模型验证，但先不复杂化

---

## 5.14 `engine/prompt_service.py`

### 目的
集中构建 prompt。

### 必须实现
#### `class PromptService`

### `def build_action_prompt(self, session: SessionState, turn: TurnState, context: dict) -> str`
### `def build_planning_prompt(self, session: SessionState, turn: TurnState, context: dict) -> str`
### `def build_verification_prompt(self, session: SessionState, turn: TurnState, context: dict) -> str`
### `def build_summary_prompt(self, session: SessionState, turn: TurnState, context: dict) -> str`

### 禁止
- 不要让其它模块到处拼 prompt

---

## 5.15 `llm/base.py`

### 目的
定义 provider 抽象。

### 必须实现
#### `class BaseLLMClient(Protocol)`
```python
class BaseLLMClient(Protocol):
    async def complete(self, prompt: str, **kwargs) -> str: ...
    async def stream(self, prompt: str, **kwargs): ...
```

---

## 5.16 `llm/zhipu_client.py`

### 目的
ZHIPU GLM 的具体实现。

### 必须实现
#### `class ZhipuClient`

### `async def complete(self, prompt: str, **kwargs) -> str`
### `async def stream(self, prompt: str, **kwargs)`

### 职责
- 调用 API
- 处理 timeout/retry
- 屏蔽 provider 细节

---

## 5.17 `llm/llm_service.py`

### 目的
对底层 client 做服务包装。

### 必须实现
#### `class LLMService`

### `__init__(self, client: BaseLLMClient, config: dict, event_bus: EventBus | None = None)`
### `async def generate(self, prompt: str) -> str`
### `async def stream(self, prompt: str)`

### 职责
- 统一模型调用入口
- 发布 llm 事件
- 做最外层错误包装

### 禁止
- 不要依赖 session internals
- 不要做 prompt 拼接

---

## 5.18 `tools/base.py`

### 目的
工具抽象基类。

### 必须实现
#### `class BaseTool`

字段：
- name: str
- description: str
- args_schema: dict

方法：
- `async def run(self, **kwargs) -> ToolResult`

---

## 5.19 `tools/registry.py`

### 目的
统一管理工具。

### 必须实现
#### `class ToolRegistry`

### `def register(self, tool: BaseTool) -> None`
### `def get(self, name: str) -> BaseTool`
### `def list_specs(self) -> list[dict]`

---

## 5.20 `tools/tool_executor.py`

### 目的
独立工具执行服务。

### 必须实现
#### `class ToolExecutor`

### `__init__(self, registry: ToolRegistry, policy_service: PolicyService, event_bus: EventBus | None = None)`
### `async def execute(self, session_id: str, turn_id: str, tool_name: str, args: dict) -> ToolResult`

### 执行流程必须固定为
1. registry.get(tool_name)
2. policy_service.check(tool_name, args)
3. deny -> 直接返回失败结果
4. ask -> 返回等待审批结果（第一版可简化为失败并提示）
5. allow -> 执行 tool.run()
6. 规范化为 ToolResult

### 禁止
- 不要在 QueryEngine 内部执行工具
- 不要直接绕过 PolicyService

---

## 5.21 `tools/file_tools.py`

### 目的
文件相关工具。

### 必须实现
#### `class ReadFileTool(BaseTool)`
输入：
- path

输出：
- 文件内容

#### `class WriteFileTool(BaseTool)`
输入：
- path
- content

输出：
- success/failure

#### `class ListDirTool(BaseTool)`
输入：
- path

输出：
- 文件列表

### 备注
可选：
- SearchInFilesTool

---

## 5.22 `tools/bash_tools.py`

### 目的
Shell 工具。

### 必须实现
#### `class BashTool(BaseTool)`
输入：
- command

输出：
- stdout / stderr / return_code

### 安全要求
第一版必须：
- 走 PolicyService
- 捕获异常
- 返回结构化结果
- 不做危险命令黑名单的复杂实现，但要预留接口

---

## 5.23 `memory/memory_store.py`

### 目的
存 memory 条目。

### 必须实现
#### `class MemoryStore`

### `def add(self, session_id: str, item: dict) -> None`
### `def get_recent(self, session_id: str, limit: int) -> list[dict]`
### `def get_all(self, session_id: str) -> list[dict]`

---

## 5.24 `memory/memory_service.py`

### 目的
记忆服务。

### 必须实现
#### `class MemoryService`

### `async def record_user_message(self, session_id: str, text: str) -> None`
### `async def record_tool_result(self, session_id: str, turn_id: str, result: ToolResult) -> None`
### `async def add_system_note(self, session_id: str, note: str) -> None`
### `async def get_recent(self, session_id: str, limit: int = 10) -> list[dict]`

### 备注
- Memory 负责“存”
- 不负责“本轮怎么组 prompt”

---

## 5.25 `context/context_service.py`

### 目的
推理上下文构造器。

### 必须实现
#### `class ContextService`

### `async def build_context(self, session: SessionState, turn: TurnState) -> dict`
返回内容建议：
```python
{
    "recent_history": [...],
    "important_memory": [...],
    "current_plan": {...} | None,
    "last_tool_result": {...} | None,
}
```

### `async def maybe_compact(self, session_id: str) -> None`
职责：
- 判断是否需要裁剪/压缩
- 第一版可做 very light compaction

### 依赖
- `memory/memory_service.py`
- `context/compactor.py`

---

## 5.26 `context/compactor.py`

### 目的
上下文压缩辅助。

### 必须实现
#### `class ContextCompactor`

### `def compact_recent_history(self, messages: list[dict], max_items: int) -> list[dict]`
### `def compact_tool_outputs(self, items: list[dict], max_chars: int) -> list[dict]`

### 备注
第一版不需要 LLM 总结压缩，先做简单裁剪即可。

---

## 5.27 `policy/policy_service.py`

### 目的
权限和审批策略。

### 必须实现
#### `class PolicyService`

### `def __init__(self, config: dict)`
### `async def check(self, tool_name: str, args: dict) -> dict`

返回示例：
```python
{"status": "allow"}
```

或

```python
{"status": "ask", "reason": "write operations require approval"}
```

或

```python
{"status": "deny", "reason": "bash disabled by policy"}
```

### 默认规则建议
- read_file / list_dir -> allow
- write_file -> ask
- bash -> ask 或 deny（由配置控制）

---

## 5.28 `tracing/tracing_service.py`

### 目的
轻量 tracing。

### 必须实现
#### `class TracingService`

### `def start_span(self, name: str, session_id: str, turn_id: str | None = None) -> object`
### `def end_span(self, span: object, metadata: dict | None = None) -> None`
### `def log_event(self, name: str, payload: dict) -> None`

### 第一版要求
- 可以仅打印日志或写到内存
- 不要引入复杂 OTEL 依赖

---

## 5.29 `utils/ids.py`

### 必须实现
- `def gen_session_id() -> str`
- `def gen_turn_id() -> str`
- `def gen_event_id() -> str`

---

## 5.30 `utils/json_utils.py`

### 必须实现
- `def extract_json_block(text: str) -> str`
- `def safe_json_loads(text: str) -> dict`

---

## 5.31 `utils/logging_utils.py`

### 必须实现
- `def get_logger(name: str)`
- 简单日志格式封装

---

# 6. 强制实现顺序

执行者必须按以下顺序实现。

## Phase 1：状态与基础设施
1. `sessions/schemas.py`
2. `sessions/session_store.py`
3. `runtime/event_types.py`
4. `runtime/event_bus.py`
5. `runtime/service_registry.py`

## Phase 2：能力服务
6. `memory/memory_store.py`
7. `memory/memory_service.py`
8. `context/compactor.py`
9. `context/context_service.py`
10. `policy/policy_service.py`
11. `tools/base.py`
12. `tools/registry.py`
13. `tools/file_tools.py`
14. `tools/bash_tools.py`
15. `tools/tool_executor.py`
16. `llm/base.py`
17. `llm/zhipu_client.py`
18. `llm/llm_service.py`

## Phase 3：engine
19. `engine/parser.py`
20. `engine/prompt_service.py`
21. `engine/planner.py`
22. `engine/verifier.py`
23. `engine/query_loop.py`
24. `engine/query_engine.py`

## Phase 4：runtime 装配
25. `sessions/session_service.py`
26. `tracing/tracing_service.py`
27. `runtime/session_runtime.py`
28. `config.py`
29. `app.py`

---

# 7. QueryEngine 与 query_loop 的边界要求（最重要）

## QueryEngine 必须做的
- 创建 turn
- 写入用户消息
- 调用 query_loop
- 保存 query_loop 返回结果
- 更新 session 状态

## QueryEngine 绝不能做的
- while-loop 推进
- 工具执行
- 具体 prompt 拼接
- 上下文压缩细节
- 模型 provider 直接调用

## query_loop 必须做的
- 单轮 turn 的 step-by-step 推进
- action 分支处理
- tool_call / finish / ask_user / replan
- verify before finish

## query_loop 绝不能做的
- session 生命周期管理
- 程序输入读取
- 配置加载
- 工具实现细节

---

# 8. 最小主流程参考

```python
async def main():
    config = load_config()
    runtime = SessionRuntime(config)
    await runtime.start()

    session_id = await runtime.create_session()

    while True:
        text = input("> ").strip()
        if text in {"/exit", "exit", "quit"}:
            break

        result = await runtime.handle_user_input(session_id, text)
        print(result.message)
```

---

# 9. QueryEngine 调用 query_loop 参考

```python
async def submit_message(self, session_id: str, user_text: str) -> QueryLoopResult:
    session = self.session_store.get_session(session_id)
    turn = self.session_store.create_turn(session_id, user_text, self.config["runtime"]["max_steps"])

    await self.session_service.append_message(session_id, "user", user_text)
    await self.memory_service.record_user_message(session_id, user_text)

    result = await query_loop(
        session=session,
        turn=turn,
        session_store=self.session_store,
        session_service=self.session_service,
        memory_service=self.memory_service,
        context_service=self.context_service,
        prompt_service=self.prompt_service,
        llm_service=self.llm_service,
        tool_executor=self.tool_executor,
        planner=self.planner,
        verifier=self.verifier,
        parser=self.parser,
        tracing_service=self.tracing_service,
    )

    return result
```

---

# 10. 执行者禁止事项

执行者在实现时不得：

- 把逻辑重新塞回 `QueryEngine`
- 把 memory/context 合并成一个文件
- 在 `app.py` 中写业务逻辑
- 在 `query_loop.py` 中直接写原始 API 请求代码
- 绕过 `ToolExecutor` 直接执行工具
- 绕过 `PolicyService` 直接执行写文件或 bash
- 加入不必要的复杂微服务/数据库/向量检索系统

---

# 11. 最终验收标准

只有满足以下条件，才算完成本次重构：

## 架构
- 程序常驻
- 有 SessionRuntime
- 有 QueryEngine
- 有独立 query_loop
- 有 ToolExecutor
- 有 LLMService
- 有 MemoryService / ContextService
- 有 SessionStore

## 行为
- 用户可以连续输入多轮任务
- 同一 session 保持历史与状态
- 每次用户输入触发一个新的 turn
- turn 内部由 query_loop 推进
- tool_call 通过 ToolExecutor 执行
- finish 必须经过 verify
- write/bash 必须经过 PolicyService

## 代码组织
- 文件职责清晰
- 无 God Object
- QueryEngine 与 query_loop 明确拆开

---

# 12. 一句话总结

本次重构的本质，不是“把旧 while-loop 改好看”，而是：

> **把 simple_agent 从单体 agent loop 重构为 Session Runtime + QueryEngine + query_loop + ToolExecutor + LLMService + Memory/Context Service 的服务化架构。**

执行者必须严格遵守这个分层，不允许回退成一个大文件大循环。
