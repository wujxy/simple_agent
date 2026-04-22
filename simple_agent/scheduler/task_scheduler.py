from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field

from simple_agent.tools.core.executor import ToolExecutor
from simple_agent.tools.core.registry import ToolRegistry
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("task_scheduler")

# Display set used by prompts to list available batch tools.
BATCHABLE_TOOLS = {"read_file", "list_dir"}

# Fallback when no registry is available.
_BATCHABLE_FALLBACK = {"read_file", "list_dir"}


@dataclass
class TaskSpec:
    task_id: str
    tool_name: str
    args: dict = field(default_factory=dict)
    deps: list[str] = field(default_factory=list)
    conflict_keys: list[str] = field(default_factory=list)
    kind: str = ""  # auto-inferred if empty: read | write | search | verify | summary | unknown


@dataclass
class TaskRuntimeState:
    task: TaskSpec
    status: str = "pending"  # pending | running | completed | failed | skipped
    result: dict | None = None


@dataclass
class ScheduleResult:
    states: list[TaskRuntimeState]
    layers_executed: int
    total_tasks: int
    completed: int
    failed: int
    skipped: int


class TaskScheduler:
    def __init__(
        self,
        tool_executor: ToolExecutor,
        *,
        registry: ToolRegistry | None = None,
        max_concurrency: int = 8,
    ) -> None:
        self._executor = tool_executor
        self._registry = registry
        self._semaphore = asyncio.Semaphore(max_concurrency)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _is_batchable(self, tool_name: str) -> bool:
        if self._registry:
            tool = self._registry.get(tool_name)
            if tool:
                return tool.spec.capabilities.read_only
        return tool_name in _BATCHABLE_FALLBACK

    def validate_batch(self, tasks: list[TaskSpec]) -> None:
        for task in tasks:
            if not self._is_batchable(task.tool_name):
                raise ValueError(
                    f"Tool '{task.tool_name}' is not batchable. "
                    f"Batchable tools are those with read_only capability."
                )

    def infer_kind(self, tool_name: str) -> str:
        if self._registry:
            tool = self._registry.get(tool_name)
            if tool:
                caps = tool.spec.capabilities
                if caps.read_only:
                    return "read"
                if caps.mutates_files:
                    return "write"
                return "other"
        return "read" if tool_name in _BATCHABLE_FALLBACK else "unknown"

    # ------------------------------------------------------------------
    # DAG: topological sort (Kahn's algorithm)
    # ------------------------------------------------------------------

    @staticmethod
    def _topological_layers(tasks: list[TaskSpec]) -> list[list[TaskSpec]]:
        """Return layers of tasks. Each layer's tasks are independent and can run in parallel."""
        if not tasks:
            return []

        task_map = {t.task_id: t for t in tasks}
        in_degree: dict[str, int] = {t.task_id: 0 for t in tasks}
        dependents: dict[str, list[str]] = defaultdict(list)

        for t in tasks:
            for dep_id in t.deps:
                if dep_id not in task_map:
                    raise ValueError(
                        f"Task '{t.task_id}' depends on unknown task '{dep_id}'"
                    )
                dependents[dep_id].append(t.task_id)
                in_degree[t.task_id] += 1

        layers: list[list[TaskSpec]] = []
        ready = [tid for tid, deg in in_degree.items() if deg == 0]

        while ready:
            layer = [task_map[tid] for tid in ready]
            layers.append(layer)
            next_ready: list[str] = []
            for tid in ready:
                for child_id in dependents[tid]:
                    in_degree[child_id] -= 1
                    if in_degree[child_id] == 0:
                        next_ready.append(child_id)
            ready = next_ready

        # Cycle detection
        sorted_count = sum(len(layer) for layer in layers)
        if sorted_count < len(tasks):
            remaining = set(task_map.keys()) - {
                tid for layer in layers for t in layer for tid in [t.task_id]
            }
            raise ValueError(f"Dependency cycle detected among tasks: {remaining}")

        return layers

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    async def schedule(
        self,
        tasks: list[TaskSpec],
        session_id: str,
        turn_id: str,
    ) -> ScheduleResult:
        self.validate_batch(tasks)

        # Auto-infer kind
        for t in tasks:
            if not t.kind:
                t.kind = self.infer_kind(t.tool_name)

        layers = self._topological_layers(tasks)

        state_map: dict[str, TaskRuntimeState] = {
            t.task_id: TaskRuntimeState(task=t) for t in tasks
        }
        failed_ancestors: set[str] = set()

        for layer in layers:
            # Determine which tasks in this layer should be skipped
            to_run: list[TaskSpec] = []
            for task in layer:
                if any(dep in failed_ancestors for dep in task.deps):
                    state_map[task.task_id].status = "skipped"
                    state_map[task.task_id].result = {
                        "tool_name": task.tool_name,
                        "ok": False,
                        "status": "skipped",
                        "error": "Skipped: dependency failed",
                    }
                    failed_ancestors.add(task.task_id)
                else:
                    to_run.append(task)

            if not to_run:
                continue

            coros = [
                self._execute_task(task, session_id, turn_id)
                for task in to_run
            ]
            results = await asyncio.gather(*coros)
            for runtime in results:
                state_map[runtime.task.task_id] = runtime
                if runtime.status == "failed":
                    failed_ancestors.add(runtime.task.task_id)

        all_states = [state_map[t.task_id] for t in tasks]
        return ScheduleResult(
            states=all_states,
            layers_executed=len(layers),
            total_tasks=len(tasks),
            completed=sum(1 for s in all_states if s.status == "completed"),
            failed=sum(1 for s in all_states if s.status == "failed"),
            skipped=sum(1 for s in all_states if s.status == "skipped"),
        )

    async def _execute_task(
        self, task: TaskSpec, session_id: str, turn_id: str,
    ) -> TaskRuntimeState:
        async with self._semaphore:
            runtime = TaskRuntimeState(task=task, status="running")
            try:
                result = await self._executor.execute(
                    session_id, turn_id, task.tool_name, task.args,
                )
                obs = result.observation
                runtime.status = "completed" if obs.ok else "failed"
                runtime.result = {
                    "tool_name": result.tool,
                    "ok": obs.ok,
                    "status": obs.status,
                    "summary": obs.summary,
                    "facts": obs.facts,
                    "data": obs.data,
                    "error": obs.error,
                    "changed_paths": obs.changed_paths,
                }
            except Exception as e:
                runtime.status = "failed"
                runtime.result = {
                    "tool_name": task.tool_name,
                    "ok": False,
                    "status": "error",
                    "error": str(e),
                }
            return runtime
