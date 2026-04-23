# simple_agent 项目总结

## 项目定位

`simple_agent` 是一个基于大语言模型的轻量级 Agent 框架。当前实现的核心目标是：在常驻会话中接收用户任务，构建上下文，调用 LLM 生成结构化动作，通过工具执行文件/命令操作，并在结束前进行验证。

项目已经从 README 中描述的早期单体 `SimpleAgent` 形态演进为 service/runtime 架构。当前主入口是 `simple_agent.app` 与 `SessionRuntime`，不是 README 示例中的 `simple_agent.agent.SimpleAgent`。

## 运行方式

安装依赖：

```bash
pip install -e ".[dev]"
```

配置智谱 API Key：

```bash
export ZHIPU_API_KEY="your-api-key"
```

启动交互式 CLI：

```bash
python -m simple_agent.app
```

入口流程：

- `simple_agent/app.py` 启动异步 CLI 循环。
- `load_config()` 读取默认配置与 `configs/` 下的 YAML。
- `SessionRuntime` 创建会话，并把用户输入交给 `handle_user_input()`。
- 如果当前 turn 正在等待审批或用户补充输入，则恢复旧 turn；否则创建新 turn。

## 核心架构

### Runtime 层

`simple_agent/runtime/session_runtime.py` 是系统装配中心，负责创建并注册核心服务：

- `SessionStore` / `SessionService`：管理 session、turn 与消息历史。
- `MemoryStore` / `MemoryService`：保存用户消息、工具结果和系统笔记。
- `ContextService`：从记忆、工作集、artifact 快照和执行状态构建 prompt 上下文。
- `PolicyEngine` + `PolicyHook` + `HookManager`：工具调用前的策略检查和审批拦截。
- `ApprovalService`：管理待审批工具调用。
- `ToolRegistry` / `ToolExecutor`：注册并执行工具。
- `LLMService` / `ZhipuClient`：封装智谱 GLM 调用。
- `QueryEngine`：管理一次用户请求的生命周期。

当前默认注册的工具包括：

- `read_file`
- `write_file`
- `list_dir`
- `bash`

### Session 与 Turn

`simple_agent/sessions/schemas.py` 定义了主要运行状态：

- `SessionState`：会话级状态，包含消息历史、当前计划、活动 turn、权限状态、上下文元信息、工作集。
- `TurnState`：单次用户请求的状态，包含 step 计数、当前动作、最后工具结果、验证结果、待处理动作。
- `QueryLoopResult`：返回给上层 CLI 的结果，状态为 `completed`、`waiting_user` 或 `failed`。

`SessionRuntime.handle_user_input()` 会根据 `session.active_turn_id` 和 `turn.mode` 分流：

- 无活动 turn：调用 `QueryEngine.submit_message()` 创建新任务。
- `waiting_user_approval`：调用 `resume_approval()` 处理用户审批。
- `waiting_user_input`：调用 `resume_user_input()` 继续执行。

## 执行引擎

### QueryEngine

`simple_agent/engine/query_engine.py` 管理 turn 生命周期：

- 创建 turn，写入用户消息到 session history 和 memory。
- 构造 `QueryState`。
- 调用 `query_loop()` 进入 step-by-step 执行循环。
- 在等待、完成或失败时同步 session/turn 状态。
- 对审批输入进行解析，支持 `/approve`、`y`、`yes`、`approve`、`ok`、`confirm`，以及对应拒绝关键词。

### QueryLoop

`simple_agent/engine/query_loop.py` 是 Agent 的核心循环。每轮执行：

1. 检查是否处于终止态或等待态。
2. 检查是否超过 `max_steps`。
3. 使用 `ContextService.build_context()` 构建上下文。
4. 使用 `PromptService.build_action_prompt()` 组装 action prompt。
5. 调用 `LLMService.generate()` 获取模型输出。
6. 使用 `ActionParser.safe_parse()` 解析 JSON 动作。
7. 使用 `dispatch_action()` 分发动作。
8. 将状态同步回 `TurnState`。

支持的动作类型：

- `tool_call`
- `tool_batch`
- `plan`
- `replan`
- `verify`
- `summarize`
- `ask_user`
- `finish`

### Dispatcher

`simple_agent/engine/dispatcher.py` 负责把结构化动作转为具体行为：

- `tool_call`：执行单个工具，记录结果，更新 artifact、working set 和 memory。
- `tool_batch`：使用 `TaskScheduler` 并发执行只读工具批次。
- `plan`：调用 Planner 生成执行计划。
- `replan`：基于当前状态重新规划。
- `verify`：调用 Verifier 检查任务是否完成。
- `summarize`：生成进度总结。
- `ask_user`：暂停并等待用户补充输入。
- `finish`：先验证，再完成任务；验证失败时会继续执行，超过验证失败次数后强制完成。

调度器还包含一个基于证据的计划步骤推进机制：工具成功后不会简单地把步骤标记为完成，而是根据 step 的 `action_type` 和工具结果先推进到 `candidate_done`，再通过后续 run/verify 等动作确认。

## Prompt 与解析

`PromptService` 将 prompt 拆成多个层次：

- system core
- trust rules
- tool contracts
- code task rules
- capability prompt
- context prompt
- user input

`ActionParser` 要求 LLM 输出可提取的 JSON 对象，并校验动作类型。它还支持把已知工具名作为 `type` 的输出自动转换为标准 `tool_call`。

示例标准动作：

```json
{
  "type": "tool_call",
  "reason": "need to inspect file",
  "tool": "read_file",
  "args": {"path": "README.md"}
}
```

## 上下文与记忆

`ContextService` 生成结构化 `PromptContext`，包括：

- `objective_block`：用户目标与计划摘要。
- `execution_state`：当前 mode、step、计划进度、最后工具结果。
- `artifact_snapshot`：最近读写文件快照、写入保证、最新 shell 结果。
- `confirmed_facts`：从成功工具结果提取的事实。
- `next_decision_point`：下一步决策提示。
- `compact_memory_summary`：会话记忆压缩摘要。
- `working_set_summary`：最近读写文件和重复动作提示。
- `recent_observations`：失败工具与最近验证状态。

`MemoryService` 当前是内存实现，保存：

- 用户消息
- 工具结果
- 系统笔记

`WorkingSet` 用于记录最近读/写文件和重复动作，帮助 prompt 避免无意义重复读写。

## 工具系统

工具继承 `BaseTool`，通过 `ToolSpec` 描述能力、输入 schema、输出 schema 和 prompt 文案。工具执行统一返回 `ToolObservation`，字段包括：

- `ok`
- `status`
- `summary`
- `facts`
- `data`
- `error`
- `retryable`
- `changed_paths`

当前工具：

- `ReadFileTool`：读取文件，可按起始行和最大行数截取，返回文件内容、总行数和截断信息。
- `WriteFileTool`：写入完整文件内容，自动创建父目录，检测 noop，并返回简要 diff 统计。
- `ListDirTool`：列出目录 entries。
- `BashTool`：异步执行 shell 命令，返回 exit code、stdout、stderr。

`ToolExecutor` 在真正执行工具前会运行 hook 链。如果策略要求审批，则返回 `approval_required`，由上层暂停 turn 并等待用户确认。

## 策略与审批

`PolicyEngine` 默认策略：

- 允许读：`read_file`、`list_dir`
- 写文件默认不直接允许，但可要求审批
- bash 默认不直接允许，但可要求审批
- 阻止包含 `rm -rf`、`mkfs`、`dd`、`format` 的 bash 命令

配置位于 `configs/policy.yaml`。当前配置还包含 `allow_network: false`，但代码中的 `PolicyEngine` 没有网络工具，也没有使用这个字段。

审批机制：

- `ToolExecutor` 发现 `ask` 决策后创建 `ApprovalRequest`。
- `QueryEngine.resume_approval()` 解析用户输入。
- 审批通过后用 `approved=True` 重新执行工具，绕过 hook。
- 同一 turn 内会记录 `ApprovalGrant`，用于复用审批。

## 批量任务调度

`simple_agent/scheduler/task_scheduler.py` 支持 `tool_batch`：

- 只允许 batchable 工具，目前通过 `read_only` capability 判断。
- 默认可批量执行 `read_file` 和 `list_dir`。
- 支持基于依赖的 DAG 分层执行。
- 同层任务通过 `asyncio.gather()` 并发执行。
- 依赖失败的任务会被标记为 skipped。

这适合一次性读取多个文件或列出多个目录，避免 LLM 多轮串行读取。

## LLM 层

当前默认使用智谱：

- `ZhipuClient` 读取 `ZHIPU_API_KEY`。
- 默认模型为 `glm-4.7`。
- 支持普通 completion、messages completion 和 stream。
- completion 内置最多 3 次重试。

`LLMService` 是薄封装，主要负责日志记录和统一调用接口。

## 配置

默认配置在 `simple_agent/config.py` 中定义：

- `runtime.max_steps`: 20
- `model.provider`: `zhipu`
- `model.model_name`: `glm-4.7`
- `model.temperature`: 0.0
- `model.max_tokens`: 4096
- `model.timeout`: 60
- `context.recent_history_limit`: 20
- `context.memory_limit`: 10
- `context.max_tool_output_chars`: 2000

当传入 `configs` 目录时，会读取：

- `configs/model.yaml`
- `configs/agent.yaml`
- `configs/policy.yaml` 的路径会被记录为 `policy_path`

需要注意：`load_config()` 当前只把 `configs/agent.yaml` 中的 `max_steps` 合并进 `runtime`，但 `enable_planning`、`planning_threshold`、`memory_window` 没有实际接入当前运行链路。`configs/policy.yaml` 的内容也没有被加载合并到 `config["policy"]`，当前代码只保存了 `policy_path`，因此运行时策略主要来自 `config.py` 默认值。

## 测试现状

项目有以下测试文件：

- `tests/test_agent.py`
- `tests/test_context_layers.py`
- `tests/test_memory.py`
- `tests/test_parser.py`
- `tests/test_planner.py`
- `tests/test_policy.py`
- `tests/test_task_scheduler.py`
- `tests/test_tools.py`

当前测试状态存在明显不一致：

- 直接运行 `pytest -q` 时，系统 pytest 入口无法导入本地 `simple_agent` 包，报 `ModuleNotFoundError: No module named 'simple_agent'`。
- 使用当前 `python` 可以正常 `import simple_agent`，但 `python -m pytest -q` 失败，因为当前解释器环境没有安装 `pytest`。
- 部分测试仍引用旧接口，例如 `simple_agent.agent.SimpleAgent`、`simple_agent.parser.ActionParser`、`simple_agent.planner.Planner`、`simple_agent.policy.PolicyChecker`、`simple_agent.memory.Memory`。这些路径与当前 service/runtime 架构不匹配。

因此，当前测试套件需要先统一 Python 环境与导入路径，然后重构旧接口测试，才能作为可靠回归测试使用。

## 当前实现的主要优点

- 架构分层清晰：runtime、engine、context、memory、tools、policy、approval 分离。
- 执行状态可恢复：turn 可以在等待审批或等待用户输入时暂停，再由用户输入恢复。
- 工具输出结构化：`ToolObservation` 为上下文、验证和计划推进提供统一证据。
- 有基础安全边界：工具调用前通过 hook/policy/approval 拦截。
- prompt 构建已经模块化：便于继续优化不同 prompt layer。
- 支持只读工具批处理：提高多文件查看类任务的效率。

## 主要风险与待改进点

- README 与测试仍描述旧架构，容易误导使用者。
- `load_config()` 未实际加载 `configs/policy.yaml` 内容，策略配置文件目前没有完整生效。
- `configs/agent.yaml` 中部分字段没有接入运行逻辑。
- `ToolExecutor` 和调度器访问了 `_registry`、`_approval_memory` 等内部属性，封装边界较弱。
- `BashTool` 使用 `asyncio.create_subprocess_shell()`，尽管有策略拦截，仍需要更严格的命令安全模型和工作目录控制。
- 记忆、session、approval 当前都是内存存储，进程退出后不会持久化。
- `ContextService` 内部持有全局 `ArtifactState`，如果多 session 并行使用，可能需要按 session 隔离。
- 测试环境和测试接口需要更新，否则难以保障后续重构安全。

## 总体评价

当前 `simple_agent` 已经具备一个最小可用自主 Agent 的核心骨架：会话运行时、LLM 动作循环、结构化工具系统、审批机制、上下文构建、计划与验证都已经成型。项目的重点已经从“能跑通单轮 demo”进入到“提高可靠性、安全性和可测试性”的阶段。

下一步最有价值的工作是：同步文档和测试到当前 runtime 架构，修复配置加载缺口，补齐 service 级回归测试，并强化 bash/文件写入等高风险工具的安全边界。
