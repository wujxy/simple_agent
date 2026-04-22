from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from simple_agent.tools.core.executor import ToolExecutor
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("task_scheduler")

BATCHABLE_TOOLS = {"read_file", "list_dir"}


@dataclass
class TaskSpec:
    task_id: str
    tool_name: str
    args: dict = field(default_factory=dict)
    deps: list[str] = field(default_factory=list)
    conflict_keys: list[str] = field(default_factory=list)
    kind: str = "read"  # read | write | search | verify | summary


@dataclass
class TaskRuntimeState:
    task: TaskSpec
    status: str = "pending"  # pending | running | completed | failed | waiting_approval
    result: dict | None = None


class TaskScheduler:
    def __init__(self, tool_executor: ToolExecutor) -> None:
        self._executor = tool_executor

    def validate_batch(self, tasks: list[TaskSpec]) -> None:
        for task in tasks:
            if task.tool_name not in BATCHABLE_TOOLS:
                raise ValueError(
                    f"Tool '{task.tool_name}' is not batchable. "
                    f"Batchable tools: {BATCHABLE_TOOLS}"
                )

    async def schedule(
        self,
        tasks: list[TaskSpec],
        session_id: str,
        turn_id: str,
    ) -> list[TaskRuntimeState]:
        self.validate_batch(tasks)

        coros = [
            self._execute_task(task, session_id, turn_id)
            for task in tasks
        ]
        return await asyncio.gather(*coros)

    async def _execute_task(
        self, task: TaskSpec, session_id: str, turn_id: str,
    ) -> TaskRuntimeState:
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
            runtime.result = {"tool_name": task.tool_name, "ok": False, "status": "error", "error": str(e)}
        return runtime
