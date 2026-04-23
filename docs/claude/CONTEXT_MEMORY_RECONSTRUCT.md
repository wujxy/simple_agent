# CONTEXT_MEMORY_RECONSTRUCT.md

## 1. 文档目标

本文档给出 `simple_agent` 当前记录服务重构为 **Context Service + Memory Service** 双层管理系统的执行方案，并补充一个可先落地的 **Compact Service v0** 设计，用于后续执行者参考与实施。

本文档解决的核心问题：

1. 当前“上下文存档”“结构化记忆”“prompt 注入”职责交叉，边界不清。
2. 当前 prompt 中注入的结构化历史太少，局部执行连续性不足。
3. `memory_service` 目前更像“记录器”，不是“受预算管理的 prompt memory 管理器”。
4. 当前 `context/compactor.py` 只是极简裁剪器，不是真正的 compact 服务。

---

## 2. 当前实现的核心现状

### 2.1 Prompt 主链路

当前主循环中，每一步执行顺序是：

`query_loop -> context_service.build_context() -> prompt_service.build_action_prompt() -> llm.generate()`

这意味着 prompt 是**每一步重建**的，而不是通过自然累积完整对话历史来形成。

### 2.2 当前 prompt 注入块

当前 `PromptContext` / `build_context()` 主要生成如下块：

- `objective_block`
- `execution_state`
- `artifact_snapshot`
- `confirmed_facts`
- `next_decision_point`
- `compact_memory_summary`
- `working_set_summary`
- `recent_observations`

其中后三项仍被 `action_prompt.py` 作为 legacy block 注入。

### 2.3 当前记录面并不只是一套

当前系统中，承担“记录/存档/回灌”作用的状态并不只有一处：

#### SessionState
- `message_history`
- `current_plan`
- `active_turn_id`
- `permission_state`
- `context_meta`
- `memory_meta`
- `working_set`

#### TurnState
- `current_action`
- `last_tool_result`
- `verification_result`
- `pending_action`
- `step_count`
- `mode`
- `max_steps`

#### 其它记录点
- `MemoryStore` / `MemoryService`
- `ContextService._artifact_state`

### 2.4 当前实现的关键问题

#### 问题 A：Context 与 Memory 职责重叠

当前 `ContextService` 一方面维护 artifact 状态与 working set 摘要，另一方面又直接从 `MemoryService` 中构建 `confirmed_facts / recent_observations / compact_memory_summary`，实际上已经侵入 memory 管理职责。

#### 问题 B：MemoryService 名不副实

当前 `MemoryService` 只负责：

- 记录 user message
- 记录 tool result
- 添加 system note
- 取最近 N 条

它没有负责：

- prompt memory 预算
- memory item 分层
- compact 触发
- compact 回写
- eviction 触发
- 输出“完整 prompt memory block”

#### 问题 C：局部执行历史没有被系统化注入 prompt

虽然 `query_loop` 中会将 `state.last_action` 写回 `TurnState.current_action`，`last_tool_result`、`verification_result` 也会同步到 `TurnState`，但这些最近步骤历史并没有被建成独立的 `recent_steps` prompt block。

#### 问题 D：当前 compact 只是极简裁剪

`context/compactor.py` 目前只有：

- `compact_recent_history(messages[-max_items:])`
- `compact_tool_outputs(output[:max_chars])`

这不是“记忆压缩服务”，只能算演示性质的轻裁剪工具。

---

## 3. 重构后的核心语义定义

本方案明确采用如下新定义：

### 3.1 Context Service

**Context Service = 全真上下文存档池**

职责：

- 保存一个 session 的完整原始历史
- 不做 prompt 预算控制
- 不直接负责 prompt memory 注入
- 为 UI 展示、debug、回放、审计、compact 提供原始素材

性质：

- 全真
- 无上限（至少概念上无上限）
- 可回源
- 不直接进 prompt

### 3.2 Memory Service

**Memory Service = 当前 prompt 全量注入的结构化记忆体**

职责：

- 定义什么信息进入 prompt memory
- 维护 memory item 的结构化表示
- 控制 budget
- 控制 hot / compacted / evicted 三层状态
- 在超预算时调用 compact service
- 输出每一步都要全量注入 prompt 的完整 memory block

性质：

- 结构化
- 受预算约束
- 每一步全量注入 prompt
- 允许 compact
- 允许 eviction

### 3.3 Compact Service

**Compact Service = 由 Memory Service 调用的记忆压缩服务**

职责：

- 将较旧的 hot memory 压缩成 compacted memory
- v0 先实现简单版
- 预留未来调用 LLM 的接口

### 3.4 Prompt Service

**Prompt Service 只负责组装，不负责管理记忆**

职责不变：

- 接收 system/tool/rules/context/memory/user_input
- 拼成最终 prompt

---

## 4. 新架构目标

重构后，系统要形成如下明确链路：

```text
Session Runtime
  ├─ ContextService       # 全真存档池
  ├─ MemoryService        # prompt memory 管理器
  │    └─ CompactService  # 记忆压缩服务
  ├─ ContextViewBuilder   # （可选）从 Context 中构建 UI/调试视图
  └─ PromptService        # 只负责 prompt 组装
```

运行期主链路调整为：

```text
query_loop
  -> context_service.append_event(...)
  -> memory_service.record_* (...)
  -> memory_service.build_prompt_memory(...)
  -> context_service.build_context_view(...)   # 非 prompt 必需信息可选
  -> prompt_service.build_action_prompt(...)
  -> llm.generate(...)
```

注意：

- `ContextService` 不再生成 `compact_memory_summary`
- `ContextService` 不再直接从 memory 里抓 `confirmed_facts / recent_observations`
- `MemoryService` 统一输出 prompt memory block

---

## 5. 旧字段 → 新职责迁移表

| 旧字段 / 旧状态 | 当前用途 | 新归属 | 迁移建议 |
|---|---|---|---|
| `SessionState.message_history` | 原始消息流水 | ContextService | 迁为 `ContextLedger.messages` |
| `SessionState.current_plan` | 当前计划快照 | ContextService + MemoryService | Context 保存计划历史；Memory 保留当前计划摘要 |
| `SessionState.active_turn_id` | 当前活跃 turn 指针 | Runtime | 保持流程控制用途，不并入 Context/Memory |
| `SessionState.permission_state` | 权限/审批状态槽位 | Runtime + ContextService | Runtime 存当前态；Context 存审批事件历史 |
| `SessionState.context_meta` | 上下文元数据槽位 | ContextService | 改为 context ledger 的索引/分页/UI 元数据 |
| `SessionState.memory_meta` | 记忆元数据槽位 | MemoryService | 改为 budget / compact / eviction 元数据 |
| `SessionState.working_set` | 最近读写文件与重复动作 | MemoryService | 并入 hot memory / working memory |
| `TurnState.current_action` | 最近一步 action | ContextService + MemoryService | Context 存原始 step event；Memory 保留 recent steps |
| `TurnState.last_tool_result` | 最近工具结果 | ContextService + MemoryService | Context 存原始 tool event；Memory 存提炼后的 memory item |
| `TurnState.verification_result` | 最近 verify 结果 | ContextService + MemoryService | Context 存原始 verify event；Memory 存“当前验证结论” |
| `TurnState.pending_action` | 等待动作 | Runtime + ContextService | Runtime 控制等待；Context 存 pending 事件 |
| `TurnState.step_count/mode/max_steps` | turn 执行状态 | Runtime + MemoryService | Runtime 持源数据；Memory 输出 execution state |
| `MemoryStore._data` | append-only 结构化记录 | MemoryService | 改成 prompt memory item store |
| `MemoryService.record_user_message()` | 记录用户消息 | MemoryService | 保留，改写为标准 memory item |
| `MemoryService.record_tool_result()` | 记录工具结果摘要 | ContextService + MemoryService | Context 保存原始 tool event；Memory 保存高价值提炼项 |
| `SessionSummaryService.get_compact_summary()` | 轻量摘要 | CompactService | 删除旧角色，替换为真正 compact 接口 |
| `ContextService._artifact_state` | 文件/命令结果投影 | ContextService | 迁为 `ContextLedger.artifacts` |
| `PromptContext.confirmed_facts` | 最近成功事实 | MemoryService 输出 | 从 ContextService 中剥离 |
| `PromptContext.recent_observations` | 最近失败观察 | MemoryService 输出 | 并入 recent steps / blockers |
| `PromptContext.working_set_summary` | working set 文本摘要 | MemoryService 输出 | 并入 hot memory |
| `PromptContext.compact_memory_summary` | compact summary 文本摘要 | MemoryService 输出 | 改为 compacted memory block |

---

## 6. 重构后的 Context Service 设计

### 6.1 Context Service 的唯一目标

Context 是全真账本，不直接用于 prompt budget。

### 6.2 推荐内部结构

```python
ContextLedger:
    messages: list[ContextMessageEvent]
    steps: list[ContextStepEvent]
    plan_history: list[PlanEvent]
    artifacts: list[ArtifactEvent]
    permission_events: list[PermissionEvent]
    meta: ContextMeta
```

### 6.3 推荐事件模型

#### ContextMessageEvent
- role
- content
- timestamp
- turn_id

#### ContextStepEvent
- step_id
- turn_id
- action
- tool_name
- tool_args
- tool_result_raw
- verification_result_raw
- status
- timestamp

#### PlanEvent
- plan_version
- overview
- steps
- changed_reason

#### ArtifactEvent
- kind: read_snapshot / write_guarantee / shell_result
- path / command
- preview
- step_id

### 6.4 Context Service 新职责

- `append_message_event(...)`
- `append_step_event(...)`
- `append_plan_event(...)`
- `append_artifact_event(...)`
- `get_raw_range(...)`
- `get_recent_steps(...)`
- `build_ui_context_view(...)`（可选）

### 6.5 Context Service 明确不再负责

- 不再负责 compact summary
- 不再直接从 memory 中取 confirmed facts
- 不再直接决定 prompt memory 注入内容
- 不再直接拼 prompt memory block

---

## 7. 重构后的 Memory Service 设计

### 7.1 Memory Service 的目标

Memory 是当前 prompt 的完整结构化记忆体，每一步都全量注入 prompt，但它有预算限制。

### 7.2 Memory Item 标准结构

建议统一为：

```python
{
  "id": "mem_xxx",
  "kind": "user|tool|system|step|summary|verify|plan",
  "state": "hot|compacted",
  "priority": "high|normal|low",
  "created_at_step": 12,
  "source_range": {"from_step": 3, "to_step": 8},
  "token_estimate": 320,

  "content": "...",
  "summary": "...",
  "facts": [...],
  "changed_paths": [...],
  "errors": [...],
  "decisions": [...],
  "verification": [...],
}
```

### 7.3 Memory 分层

#### Hot Memory
- 最近若干步历史
- 无损
- 高优先级
- 直接进入 prompt

#### Compacted Memory
- 由较旧 hot memory 压缩而来
- 结构化 summary
- 仍然进入 prompt

#### Evicted Memory
- 超预算后彻底移除出 prompt memory
- 可选保留最轻边界标记

### 7.4 Memory Service 新职责

- `record_user_message(...)`
- `record_tool_result(...)`
- `record_step_event(...)`
- `record_verify_result(...)`
- `record_plan_snapshot(...)`
- `build_prompt_memory(...)`
- `estimate_memory_size(...)`
- `maybe_compact(...)`
- `maybe_evict(...)`

### 7.5 Memory Meta 建议字段

```python
{
  "char_budget": 12000,
  "token_budget": null,
  "trigger_ratio": 0.8,
  "hot_keep_last": 8,
  "last_compact_at_step": 0,
  "compacted_segments": [],
  "evicted_before_step": null,
}
```

---

## 8. Compact Service v0 设计

## 8.1 v0 的目标

实现一个能闭环工作的 compact 服务，但不追求复杂策略。

v0 只需要保证：

1. budget 超阈值时可触发
2. 较旧 hot memory 可压成 1 条 compacted summary
3. compact 后回写 memory store
4. 若仍超预算，可淘汰最旧 compacted summary
5. 预留未来接入 LLM compact 的接口

### 8.2 v0 不做的事

- 不做多模式压缩（BASE/PARTIAL/UP_TO）
- 不做复杂优先级学习
- 不做 token 精算
- 不做 preserve 指令
- 不做多轮嵌套 compact

### 8.3 预算策略

v0 先用**字符数预算**，不要一开始就做 tokenizer 依赖。

推荐默认值：

```python
MEMORY_CHAR_BUDGET = 12000
COMPACT_TRIGGER_RATIO = 0.8
HOT_KEEP_LAST = 8
MIN_COMPACT_CANDIDATES = 6
```

### 8.4 v0 的 compact 触发条件

当：

```python
rendered_memory_chars > char_budget * trigger_ratio
```

则触发 compact。

### 8.5 v0 的 compact 对象选择规则

默认压缩对象：

- `state == hot`
- 不在最近 `HOT_KEEP_LAST` 条
- 非高优先级永久保留项

默认保留项：

- 最近 8 条 hot memory
- 最近一次 verify 结果
- 最近一次失败错误
- 最近一次 blocker
- 最近一次包含 `changed_paths` 的关键修改项

### 8.6 v0 的 compact 输出

compact 后输出一条 `kind=summary, state=compacted` 的 memory item。

推荐 summary schema：

```json
{
  "completed_work": ["..."],
  "active_context": ["..."],
  "modified_files": ["path: reason"],
  "open_issues": ["..."],
  "verified_results": ["..."],
  "important_errors": ["..."],
  "important_decisions": ["decision + reason"]
}
```

### 8.7 v0 compact 实现模式

#### 阶段 A：先实现 rule-based stub

在没有接 LLM 前，先用规则拼接 compact summary：

- 收集候选区里的 summary/facts/changed_paths/errors/verification
- 生成一个结构化 summary item
- 跑通回写与 eviction 主链路

#### 阶段 B：预留 LLM compact 接口

后续替换 stub 的生成逻辑即可。

建议接口：

```python
class CompactService:
    async def compact_items(
        self,
        items: list[dict],
        *,
        current_step: int,
        preserve_schema: dict | None = None,
    ) -> dict:
        ...
```

### 8.8 v0 未来的 LLM 接口预留

CompactService 内部保留一个可替换方法：

```python
async def _generate_summary_via_llm(self, items: list[dict]) -> dict:
    raise NotImplementedError
```

初版先使用：

```python
def _generate_summary_stub(self, items: list[dict]) -> dict:
    ...
```

以后切换时只替换该方法即可，不动主流程。

### 8.9 v0 的 eviction 规则

如果 compact 后仍超预算：

1. 仅淘汰 `state=compacted` 的最旧 summary
2. 不淘汰 hot memory
3. 每淘汰一次重算长度
4. 直到回到预算内

可选保留边界项：

```python
{
  "kind": "system",
  "state": "compacted",
  "summary": "Older compacted memory before step 42 has been evicted."
}
```

---

## 9. Compact Service v0 伪代码

```python
class CompactService:
    def __init__(self, char_budget: int = 12000, trigger_ratio: float = 0.8, hot_keep_last: int = 8):
        self.char_budget = char_budget
        self.trigger_ratio = trigger_ratio
        self.hot_keep_last = hot_keep_last

    async def maybe_compact(self, items: list[dict], *, current_step: int) -> dict:
        size = self._estimate_chars(items)
        if size <= self.char_budget * self.trigger_ratio:
            return {
                "did_compact": False,
                "new_items": items,
                "before_size": size,
                "after_size": size,
                "replaced_count": 0,
                "evicted_count": 0,
            }

        hot_items = items[-self.hot_keep_last:]
        prefix_items = items[:-self.hot_keep_last]

        candidates = [x for x in prefix_items if x.get("state", "hot") == "hot"]
        if len(candidates) < 6:
            return {
                "did_compact": False,
                "new_items": items,
                "before_size": size,
                "after_size": size,
                "replaced_count": 0,
                "evicted_count": 0,
            }

        summary_payload = self._generate_summary_stub(candidates)
        summary_item = {
            "id": f"mem_summary_{current_step}",
            "kind": "summary",
            "state": "compacted",
            "created_at_step": current_step,
            "source_range": {
                "from_step": candidates[0].get("created_at_step", 0),
                "to_step": candidates[-1].get("created_at_step", current_step),
            },
            "summary": summary_payload,
        }

        kept_prefix = [x for x in prefix_items if x not in candidates]
        new_items = kept_prefix + [summary_item] + hot_items

        evicted_count = 0
        while self._estimate_chars(new_items) > self.char_budget:
            oldest_compacted_idx = self._find_oldest_compacted_index(new_items)
            if oldest_compacted_idx is None:
                break
            del new_items[oldest_compacted_idx]
            evicted_count += 1

        return {
            "did_compact": True,
            "new_items": new_items,
            "summary_item": summary_item,
            "before_size": size,
            "after_size": self._estimate_chars(new_items),
            "replaced_count": len(candidates),
            "evicted_count": evicted_count,
        }
```

---

## 10. 新接口建议

## 10.1 Context Service 新接口

```python
class ContextService:
    async def append_message_event(self, session_id: str, role: str, content: str, turn_id: str | None = None) -> None: ...
    async def append_step_event(self, session_id: str, turn_id: str, step_id: int, payload: dict) -> None: ...
    async def append_plan_event(self, session_id: str, payload: dict) -> None: ...
    async def append_artifact_event(self, session_id: str, payload: dict) -> None: ...
    async def get_recent_steps(self, session_id: str, limit: int = 20) -> list[dict]: ...
    async def get_raw_segment(self, session_id: str, start_step: int, end_step: int) -> list[dict]: ...
```

## 10.2 Memory Service 新接口

```python
class MemoryService:
    async def record_user_message(self, session_id: str, text: str, *, step: int | None = None) -> None: ...
    async def record_tool_result(self, session_id: str, turn_id: str, result: dict, *, step: int | None = None) -> None: ...
    async def record_step_event(self, session_id: str, payload: dict) -> None: ...
    async def record_verify_result(self, session_id: str, payload: dict) -> None: ...
    async def build_prompt_memory(self, session_id: str, *, current_step: int) -> str: ...
```

## 10.3 Memory Store 新接口

当前 `MemoryStore` 只有：

- `add`
- `get_recent`
- `get_all`

需要新增：

```python
class MemoryStore:
    def replace_all(self, session_id: str, items: list[dict]) -> None: ...
```

这是 compact 回写的最低必要接口。

## 10.4 Compact Service 接口

```python
class CompactService:
    async def maybe_compact(
        self,
        items: list[dict],
        *,
        current_step: int,
        char_budget: int,
        trigger_ratio: float = 0.8,
        hot_keep_last: int = 8,
    ) -> dict:
        ...
```

---

## 11. Prompt 层改造建议

### 11.1 新 PromptContext 字段

新增：

- `prompt_memory_block`

保留：

- `objective_block`
- `execution_state`
- `artifact_snapshot`（可后续再讨论是否进入 memory）
- `next_decision_point`

### 11.2 删除旧 legacy memory 注入方式

逐步废弃：

- `working_set_summary`
- `recent_observations`
- `compact_memory_summary`
- `confirmed_facts`（后续也可并入 memory）

### 11.3 新的 context prompt 结构建议

```text
Block 1: Objective
Block 2: Execution state
Block 3: Prompt memory
Block 4: Artifact snapshot
Block 5: Next decision point
```

说明：

- `Prompt memory` 由 MemoryService 统一产出
- `ContextService` 不再私自拼 memory 相关块

---

## 12. 对现有文件的逐文件执行方案

## 12.1 `simple_agent/sessions/schemas.py`

### 目标
明确新职责边界。

### 建议修改

- 保留 `message_history`，但标注为“原始上下文存档，不直接用于 prompt memory”
- `working_set` 标记为待迁移到 memory service
- `context_meta`、`memory_meta` 补充注释说明职责
- 后续可新增 `context_pool_id` / `memory_state_version`（非 v0 必须）

---

## 12.2 `simple_agent/context/context_service.py`

### 目标
去掉 prompt memory 管理职责，收敛为 context 账本服务。

### 第一阶段改造

- 保留 `artifact_state` 管理
- 保留 `update_artifacts_from_tool()`
- `build_context()` 中移除：
  - `_build_confirmed_facts()`
  - `_build_recent_observations()`
  - `SessionSummaryService.get_compact_summary()`
  - `_build_working_set()`
- 新增从 `MemoryService.build_prompt_memory()` 获取 `prompt_memory_block`

### 第二阶段改造

- 增加原始 context ledger 的 append/get 接口
- 将 `message_history`、step 事件、artifact 事件整合到 ContextService 下

---

## 12.3 `simple_agent/memory/memory_store.py`

### 目标
从 append-only 日志容器升级为可 compact 回写的 store。

### 必改项

新增：

```python
def replace_all(self, session_id: str, items: list[dict]) -> None:
    self._data[session_id] = list(items)
```

可选新增：

- `clear(session_id)`
- `count(session_id)`

---

## 12.4 `simple_agent/memory/memory_service.py`

### 目标
升级为真正的 prompt memory 管理器。

### 第一阶段改造

- 删除 `SessionSummaryService` 的 compact 职责
- 引入 `CompactService`
- 规范 memory item schema
- 新增：
  - `record_step_event()`
  - `record_verify_result()`
  - `build_prompt_memory()`
  - `_render_memory_items()`
  - `_estimate_memory_size()`
  - `_maybe_compact_and_replace()`

### `build_prompt_memory()` 建议流程

```python
items = self._store.get_all(session_id)
result = await self._compact_service.maybe_compact(items, current_step=current_step, ...)
if result["did_compact"]:
    self._store.replace_all(session_id, result["new_items"])
return self._render_memory_items(result["new_items"])
```

---

## 12.5 新增 `simple_agent/memory/compact_service.py`

### 目标
实现 compact v0。

### 必须包含

- `CompactService`
- `_estimate_chars()`
- `_generate_summary_stub()`
- `_find_oldest_compacted_index()`
- `maybe_compact()`
- 预留 `_generate_summary_via_llm()` 接口

---

## 12.6 `simple_agent/context/compactor.py`

### 建议

- 直接废弃旧职责，或保留为 deprecated compatibility helper
- 不再作为未来 compact 的主实现位置

理由：

当前这个文件过于极简，继续在这里叠功能会让“context 压缩”和“memory compact”继续混淆。

---

## 12.7 `simple_agent/prompts/action_prompt.py`

### 目标
让 PromptContext 从“多块 legacy 摘要拼接”改成“统一的 prompt memory block”。

### 建议修改

- `build_context_prompt()` 中新增：
  - `if prompt_context.prompt_memory_block: ...`
- 删除 legacy block：
  - working set
  - recent observations
  - compact summary
- 后续再决定是否把 `confirmed_facts` 合入 memory block

---

## 12.8 `simple_agent/engine/query_loop.py`

### 目标
保持主循环不大改，但在合适位置补充新记录。

### 建议修改

#### 在 parse 成功后
记录 action step event：

```python
await deps.memory_service.record_step_event(...)
await deps.context_service.append_step_event(...)
```

#### 在 dispatch 结果后
记录 tool/verify 相关事件：

```python
await deps.context_service.append_step_event(...)
await deps.memory_service.record_tool_result(...)
```

#### 在 build_context 之前
不需要显式调用 compact；由 `build_context()` 内部触发 `memory_service.build_prompt_memory()` 即可。

---

## 13. 实施顺序建议

## Phase 1：职责切分先落地（不接 LLM compact）

目标：先把职责边界摆正。

执行：

1. 新增 `memory/compact_service.py`
2. 给 `MemoryStore` 增加 `replace_all()`
3. 给 `MemoryService` 增加 `build_prompt_memory()`
4. `ContextService.build_context()` 改为调用 `build_prompt_memory()`
5. `action_prompt.py` 注入 `prompt_memory_block`
6. 旧 legacy block 暂不删除，但不再新增依赖

## Phase 2：把 working_set / recent_observations / compact_summary 逐步吃进 memory

目标：Memory 成为唯一 prompt memory 来源。

执行：

1. `working_set` 内容迁成 hot memory item
2. 最近失败观察迁入 recent steps / blockers
3. 删除 `SessionSummaryService`
4. 删除 `compact_memory_summary` 注入路径

## Phase 3：接入真正 LLM compact

目标：把 v0 stub 换成 LLM 驱动 compact。

执行：

1. CompactService 增加 LLM 依赖注入
2. 使用固定 JSON schema 产出 compact summary
3. 增加 parse / fallback 逻辑
4. 加入 preserve 字段控制（后续版本）

---

## 14. Compact v0 的验收标准

### 最小验收标准

1. 当 memory 不超预算时，prompt memory 可正常构建
2. 当 memory 超过 80% 阈值时，compact v0 可触发
3. compact 后旧 hot memory 被 1 条 summary item 替换
4. compact 结果成功回写 `MemoryStore`
5. 压完仍超预算时，可淘汰最旧 compacted summary
6. `query_loop` 无需大改即可正常跑通
7. prompt 中能够看到统一的 `prompt_memory_block`

### 不要求在 v0 完成的内容

- 最优摘要质量
- 多轮历史 preserve
- token 级精算预算
- UI 级历史分页
- 子代理隔离上下文

---

## 15. 风险与注意事项

### 风险 1：过早删除 legacy block 会影响当前效果

建议先增加 `prompt_memory_block`，再逐步移除旧块，避免一次性删除导致 prompt 信息断崖。

### 风险 2：compact stub 质量一般

v0 的目标是先打通“压缩-回写-注入”闭环，不追求摘要质量极致。

### 风险 3：Context 与 Memory 双写期会增加复杂度

短期内允许双写：

- Context 保留原始记录
- Memory 保留结构化 item

这是合理过渡，不需要一开始强行单写。

### 风险 4：缺乏最近步骤历史会削弱收益

如果不补 `record_step_event()`，即使 compact 服务做好了，memory 仍然会缺少最近局部执行链，收益会被打折。

---

## 16. 推荐的最终结论

本次重构的核心不是“继续优化 context_service”，而是：

1. **把 ContextService 还原为全真账本服务**
2. **把 MemoryService 升级为 prompt memory 管理器**
3. **把 compact 从轻量裁剪提升为 memory 生命周期的一部分**

最终形成的原则应当是：

- **Context 负责存真，不负责 prompt 预算**
- **Memory 负责给模型看的当前完整记忆体**
- **Compact 负责在预算压力下把旧 memory 变成更紧凑的 memory**
- **Prompt 只负责组装，不负责决定记忆策略**

这套边界一旦落地，后续无论是加强 UI 展示、引入真正 LLM compact、还是扩展更复杂的 memory 生命周期，都会明显更顺。

---

## 17. 建议执行者的第一批实际改动

如果只做最小闭环，建议第一批改动按下面顺序执行：

1. `memory/memory_store.py`
   - 新增 `replace_all()`

2. 新增 `memory/compact_service.py`
   - 实现 compact v0 stub

3. `memory/memory_service.py`
   - 接入 CompactService
   - 增加 `build_prompt_memory()`

4. `context/context_service.py`
   - 删除 `SessionSummaryService` 依赖
   - 改为读取 `prompt_memory_block`

5. `prompts/action_prompt.py`
   - 注入 `prompt_memory_block`
   - legacy block 保留但降低依赖

6. `engine/query_loop.py`
   - 增加 `record_step_event()` / context step append 钩子

做到这一步，系统就已经从“多个记录面杂糅”迈入“Context + Memory + Compact”的基本新架构。
