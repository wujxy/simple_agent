from __future__ import annotations

from simple_agent.approval.approval_store import ApprovalStore
from simple_agent.approval.approval_service import ApprovalService
from simple_agent.context.context_service import ContextService
from simple_agent.engine.parser import ActionParser
from simple_agent.engine.planner import Planner
from simple_agent.engine.prompt_service import PromptService
from simple_agent.engine.query_engine import QueryEngine
from simple_agent.engine.verifier import Verifier
from simple_agent.hooks.hook_manager import HookManager
from simple_agent.llm.llm_service import LLMService
from simple_agent.llm.zhipu_client import ZhipuClient
from simple_agent.memory.memory_service import MemoryService, SessionSummaryService
from simple_agent.memory.memory_store import MemoryStore
from simple_agent.policy.policy_engine import PolicyEngine, PolicyHook
from simple_agent.runtime.event_bus import EventBus
from simple_agent.runtime.service_registry import ServiceRegistry
from simple_agent.sessions.session_service import SessionService
from simple_agent.sessions.session_store import SessionStore
from simple_agent.sessions.schemas import QueryLoopResult
from simple_agent.tools.bash_tools import BashTool
from simple_agent.tools.file_tools import ListDirTool, ReadFileTool, WriteFileTool
from simple_agent.tools.registry import ToolRegistry
from simple_agent.tools.tool_executor import ToolExecutor
from simple_agent.tracing.tracing_service import TracingService
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("session_runtime")


class SessionRuntime:
    def __init__(self, config: dict) -> None:
        self._config = config
        self._event_bus = EventBus()
        self._registry = ServiceRegistry()
        self._session_store = SessionStore()

        # Infrastructure
        memory_store = MemoryStore()
        memory_service = MemoryService(memory_store)
        self._registry.register("memory_store", memory_store)
        self._registry.register("memory_service", memory_service)

        summary_service = SessionSummaryService(memory_service)
        self._registry.register("summary_service", summary_service)

        session_service = SessionService(self._session_store, self._event_bus)
        self._registry.register("session_service", session_service)

        context_service = ContextService(memory_service, config.get("context"))
        self._registry.register("context_service", context_service)

        # Hook-based policy
        policy_engine = PolicyEngine(config.get("policy"))
        policy_hook = PolicyHook(policy_engine)
        hook_manager = HookManager([policy_hook])
        self._registry.register("policy_engine", policy_engine)

        # Approval service
        approval_store = ApprovalStore()
        approval_service = ApprovalService(approval_store)
        self._approval_service = approval_service
        self._registry.register("approval_service", approval_service)

        # Tools
        tool_registry = ToolRegistry()
        tool_registry.register(ReadFileTool())
        tool_registry.register(WriteFileTool())
        tool_registry.register(ListDirTool())
        tool_registry.register(BashTool())
        self._registry.register("tool_registry", tool_registry)

        tool_executor = ToolExecutor(tool_registry, hook_manager, approval_service)
        self._registry.register("tool_executor", tool_executor)

        # LLM
        model_cfg = config.get("model", {})
        llm_client = ZhipuClient(
            model=model_cfg.get("model_name", "glm-4.7"),
            temperature=model_cfg.get("temperature", 0.0),
            max_tokens=model_cfg.get("max_tokens", 4096),
            timeout=model_cfg.get("timeout", 60),
        )
        llm_service = LLMService(llm_client, model_cfg)
        self._registry.register("llm_service", llm_service)

        # Engine
        prompt_service = PromptService()
        parser = ActionParser()
        planner = Planner(llm_service)
        verifier = Verifier(llm_service)
        tracing_service = TracingService()

        self._query_engine = QueryEngine(
            session_store=self._session_store,
            session_service=session_service,
            memory_service=memory_service,
            context_service=context_service,
            prompt_service=prompt_service,
            llm_service=llm_service,
            tool_executor=tool_executor,
            planner=planner,
            verifier=verifier,
            parser=parser,
            tracing_service=tracing_service,
            approval_service=approval_service,
            config=config,
        )

    async def start(self) -> None:
        logger.info("SessionRuntime started")

    async def stop(self) -> None:
        logger.info("SessionRuntime stopped")

    async def create_session(self, cwd: str | None = None) -> str:
        session = self._session_store.create_session(cwd)
        logger.info("Created session: %s", session.session_id)
        return session.session_id

    async def handle_user_input(self, session_id: str, text: str) -> QueryLoopResult:
        session = self._session_store.get_session(session_id)
        if session is None:
            return QueryLoopResult(status="failed", message=f"Session '{session_id}' not found")

        # Route based on active turn state
        if session.active_turn_id:
            turn = self._session_store.get_turn(session.active_turn_id)
            if turn and turn.mode == "waiting_user_approval":
                return await self._query_engine.resume_approval(session_id, text)
            elif turn and turn.mode == "waiting_user_input":
                return await self._query_engine.resume_user_input(session_id, text)

        # No active turn → create new turn
        return await self._query_engine.submit_message(session_id, text)
