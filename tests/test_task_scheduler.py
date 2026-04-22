import asyncio

import pytest
from simple_agent.scheduler.task_scheduler import (
    BATCHABLE_TOOLS,
    ScheduleResult,
    TaskRuntimeState,
    TaskScheduler,
    TaskSpec,
)


class TestTaskSpec:
    def test_creation(self):
        spec = TaskSpec(task_id="t1", tool_name="read_file", args={"path": "a.py"})
        assert spec.tool_name == "read_file"
        assert spec.kind == ""  # auto-inferred, not set by default
        assert spec.conflict_keys == []
        assert spec.deps == []


class TestTaskRuntimeState:
    def test_default_status(self):
        spec = TaskSpec(task_id="t1", tool_name="read_file", args={"path": "a.py"})
        state = TaskRuntimeState(task=spec)
        assert state.status == "pending"
        assert state.result is None


class TestTopologicalSort:
    def test_single_layer_no_deps(self):
        tasks = [
            TaskSpec(task_id="t1", tool_name="read_file"),
            TaskSpec(task_id="t2", tool_name="read_file"),
        ]
        layers = TaskScheduler._topological_layers(tasks)
        assert len(layers) == 1
        assert len(layers[0]) == 2

    def test_two_layers_linear_chain(self):
        tasks = [
            TaskSpec(task_id="t1", tool_name="read_file", deps=[]),
            TaskSpec(task_id="t2", tool_name="read_file", deps=["t1"]),
            TaskSpec(task_id="t3", tool_name="read_file", deps=["t2"]),
        ]
        layers = TaskScheduler._topological_layers(tasks)
        assert len(layers) == 3
        assert [t.task_id for t in layers[0]] == ["t1"]
        assert [t.task_id for t in layers[1]] == ["t2"]
        assert [t.task_id for t in layers[2]] == ["t3"]

    def test_diamond_dependency(self):
        tasks = [
            TaskSpec(task_id="t1", tool_name="read_file", deps=[]),
            TaskSpec(task_id="t2", tool_name="read_file", deps=["t1"]),
            TaskSpec(task_id="t3", tool_name="read_file", deps=["t1"]),
            TaskSpec(task_id="t4", tool_name="read_file", deps=["t2", "t3"]),
        ]
        layers = TaskScheduler._topological_layers(tasks)
        assert len(layers) == 3
        assert [t.task_id for t in layers[0]] == ["t1"]
        assert {t.task_id for t in layers[1]} == {"t2", "t3"}
        assert [t.task_id for t in layers[2]] == ["t4"]

    def test_cycle_detection_raises(self):
        tasks = [
            TaskSpec(task_id="t1", tool_name="read_file", deps=["t2"]),
            TaskSpec(task_id="t2", tool_name="read_file", deps=["t1"]),
        ]
        with pytest.raises(ValueError, match="cycle"):
            TaskScheduler._topological_layers(tasks)

    def test_unknown_dep_raises(self):
        tasks = [
            TaskSpec(task_id="t1", tool_name="read_file", deps=["nonexistent"]),
        ]
        with pytest.raises(ValueError, match="unknown task"):
            TaskScheduler._topological_layers(tasks)

    def test_empty_task_list(self):
        layers = TaskScheduler._topological_layers([])
        assert layers == []


class TestToolClassification:
    def test_is_batchable_read_file(self):
        scheduler = TaskScheduler.__new__(TaskScheduler)
        scheduler._registry = None
        assert scheduler._is_batchable("read_file") is True

    def test_is_batchable_list_dir(self):
        scheduler = TaskScheduler.__new__(TaskScheduler)
        scheduler._registry = None
        assert scheduler._is_batchable("list_dir") is True

    def test_is_batchable_write_file(self):
        scheduler = TaskScheduler.__new__(TaskScheduler)
        scheduler._registry = None
        assert scheduler._is_batchable("write_file") is False

    def test_is_batchable_bash(self):
        scheduler = TaskScheduler.__new__(TaskScheduler)
        scheduler._registry = None
        assert scheduler._is_batchable("bash") is False

    def test_is_batchable_via_registry(self):
        from simple_agent.tools.core.registry import ToolRegistry
        from simple_agent.tools.read_file import ReadFileTool
        from simple_agent.tools.write_file import WriteFileTool

        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())

        scheduler = TaskScheduler.__new__(TaskScheduler)
        scheduler._registry = registry
        assert scheduler._is_batchable("read_file") is True
        assert scheduler._is_batchable("write_file") is False


class TestFailurePropagation:
    @pytest.mark.asyncio
    async def test_dependent_skipped_on_failure(self):
        """If t1 fails and t2 depends on t1, t2 is skipped."""
        results = await self._schedule_with_first_failing()
        assert results.states[0].status == "failed"
        assert results.states[1].status == "skipped"

    @pytest.mark.asyncio
    async def test_transitive_skip(self):
        """t1 fails → t2 skipped → t3 skipped (transitive)."""
        results = await self._schedule_chain_with_first_failing()
        assert results.states[0].status == "failed"
        assert results.states[1].status == "skipped"
        assert results.states[2].status == "skipped"

    async def _schedule_with_first_failing(self):
        from simple_agent.tools.core.executor import ToolExecutor

        class FailExecutor:
            async def execute(self, session_id, turn_id, tool_name, args, **kw):
                from simple_agent.schemas import ToolResult
                from simple_agent.tools.core.types import ToolObservation
                return ToolResult(
                    observation=ToolObservation(ok=False, status="error", error="test fail"),
                    tool=tool_name, args=args,
                )

        scheduler = TaskScheduler(FailExecutor())
        specs = [
            TaskSpec(task_id="t1", tool_name="read_file", args={"path": "a.py"}),
            TaskSpec(task_id="t2", tool_name="read_file", args={"path": "b.py"}, deps=["t1"]),
        ]
        # Bypass validate_batch since FailExecutor isn't a real ToolExecutor
        return await scheduler.schedule(specs, "s1", "t1")

    async def _schedule_chain_with_first_failing(self):
        from simple_agent.schemas import ToolResult
        from simple_agent.tools.core.types import ToolObservation

        class FailExecutor:
            async def execute(self, session_id, turn_id, tool_name, args, **kw):
                return ToolResult(
                    observation=ToolObservation(ok=False, status="error", error="test fail"),
                    tool=tool_name, args=args,
                )

        scheduler = TaskScheduler(FailExecutor())
        specs = [
            TaskSpec(task_id="t1", tool_name="read_file", args={"path": "a.py"}),
            TaskSpec(task_id="t2", tool_name="read_file", args={"path": "b.py"}, deps=["t1"]),
            TaskSpec(task_id="t3", tool_name="read_file", args={"path": "c.py"}, deps=["t2"]),
        ]
        return await scheduler.schedule(specs, "s1", "t1")


class TestConcurrencyControl:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """With max_concurrency=2, at most 2 tasks run simultaneously."""
        from simple_agent.schemas import ToolResult
        from simple_agent.tools.core.types import ToolObservation

        peak = 0
        current = 0
        lock = asyncio.Lock()

        class SlowExecutor:
            async def execute(self, session_id, turn_id, tool_name, args, **kw):
                nonlocal peak, current
                async with lock:
                    current += 1
                    if current > peak:
                        peak = current
                await asyncio.sleep(0.05)
                async with lock:
                    current -= 1
                return ToolResult(
                    observation=ToolObservation(ok=True, status="success", summary="ok"),
                    tool=tool_name, args=args,
                )

        scheduler = TaskScheduler(SlowExecutor(), max_concurrency=2)
        specs = [
            TaskSpec(task_id=f"t{i}", tool_name="read_file", args={"path": f"f{i}.py"})
            for i in range(6)
        ]
        result = await scheduler.schedule(specs, "s1", "t1")
        assert peak <= 2
        assert result.completed == 6


class TestScheduleResult:
    @pytest.mark.asyncio
    async def test_returns_schedule_result(self):
        from simple_agent.approval.approval_store import ApprovalStore
        from simple_agent.approval.approval_service import ApprovalService
        from simple_agent.hooks.hook_manager import HookManager
        from simple_agent.policy.policy_engine import PolicyHook, PolicyEngine
        from simple_agent.tools.core.registry import ToolRegistry
        from simple_agent.tools.read_file import ReadFileTool
        from simple_agent.tools.write_file import WriteFileTool
        from simple_agent.tools.core.executor import ToolExecutor

        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        hook_manager = HookManager([PolicyHook(PolicyEngine({}))])
        approval_service = ApprovalService(ApprovalStore())
        executor = ToolExecutor(registry, hook_manager, approval_service)

        scheduler = TaskScheduler(executor, registry=registry)
        specs = [
            TaskSpec(task_id="t1", tool_name="read_file", args={"path": "/nonexistent/a.py"}),
            TaskSpec(task_id="t2", tool_name="read_file", args={"path": "/nonexistent/b.py"}),
        ]
        result = await scheduler.schedule(specs, session_id="s1", turn_id="t1")
        assert isinstance(result, ScheduleResult)
        assert result.total_tasks == 2
        assert result.layers_executed == 1
        assert len(result.states) == 2

    @pytest.mark.asyncio
    async def test_rejects_write_in_batch(self):
        scheduler = TaskScheduler(None)
        specs = [
            TaskSpec(task_id="t1", tool_name="read_file", args={"path": "a.py"}),
            TaskSpec(task_id="t2", tool_name="write_file", args={"path": "b.py", "content": "x"}),
        ]
        with pytest.raises(ValueError, match="write_file"):
            scheduler.validate_batch(specs)
