import pytest
from simple_agent.scheduler.task_scheduler import TaskSpec, TaskRuntimeState, TaskScheduler


class TestTaskSpec:
    def test_creation(self):
        spec = TaskSpec(task_id="t1", tool_name="read_file", args={"path": "a.py"})
        assert spec.tool_name == "read_file"
        assert spec.kind == "read"
        assert spec.conflict_keys == []


class TestTaskRuntimeState:
    def test_default_status(self):
        spec = TaskSpec(task_id="t1", tool_name="read_file", args={"path": "a.py"})
        state = TaskRuntimeState(task=spec)
        assert state.status == "pending"
        assert state.result is None


class TestTaskScheduler:
    @pytest.mark.asyncio
    async def test_schedule_parallel_reads(self):
        from simple_agent.approval.approval_store import ApprovalStore
        from simple_agent.approval.approval_service import ApprovalService
        from simple_agent.hooks.hook_manager import HookManager
        from simple_agent.policy.policy_engine import PolicyHook, PolicyEngine
        from simple_agent.tools.registry import ToolRegistry
        from simple_agent.tools.read_file import ReadFileTool
        from simple_agent.tools.write_file import WriteFileTool
        from simple_agent.tools.tool_executor import ToolExecutor

        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        hook_manager = HookManager([PolicyHook(PolicyEngine({}))])
        approval_service = ApprovalService(ApprovalStore())
        executor = ToolExecutor(registry, hook_manager, approval_service)

        scheduler = TaskScheduler(executor)
        specs = [
            TaskSpec(task_id="t1", tool_name="read_file", args={"path": "/nonexistent/a.py"}),
            TaskSpec(task_id="t2", tool_name="read_file", args={"path": "/nonexistent/b.py"}),
        ]
        results = await scheduler.schedule(specs, session_id="s1", turn_id="t1")
        assert len(results) == 2
        assert all(r.status in ("completed", "failed") for r in results)

    @pytest.mark.asyncio
    async def test_rejects_write_in_batch(self):
        scheduler = TaskScheduler(None)
        specs = [
            TaskSpec(task_id="t1", tool_name="read_file", args={"path": "a.py"}),
            TaskSpec(task_id="t2", tool_name="write_file", args={"path": "b.py", "content": "x"}),
        ]
        with pytest.raises(ValueError, match="write_file"):
            scheduler.validate_batch(specs)
