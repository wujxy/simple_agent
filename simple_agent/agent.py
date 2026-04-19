from __future__ import annotations

from pathlib import Path

import yaml

from simple_agent.executor import Executor
from simple_agent.llm.base import BaseLLMClient
from simple_agent.llm.zhipu_client import ZhipuClient
from simple_agent.memory import Memory
from simple_agent.parser import ActionParser, ParseError
from simple_agent.planner import Planner
from simple_agent.policy import PolicyChecker
from simple_agent.prompts.action_prompt import build_action_prompt
from simple_agent.prompts.summary_prompt import build_summary_prompt
from simple_agent.prompts.verify_prompt import build_verify_prompt
from simple_agent.schemas import AgentAction
from simple_agent.state import StateManager
from simple_agent.tools.bash_tools import BashTool
from simple_agent.tools.file_tools import ListDirTool, ReadFileTool, WriteFileTool
from simple_agent.tools.registry import ToolRegistry
from simple_agent.utils.json_utils import extract_json_from_text
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("agent")


class SimpleAgent:
    def __init__(
        self,
        llm: BaseLLMClient,
        policy: PolicyChecker,
        max_steps: int = 20,
        enable_planning: bool = True,
        planning_threshold: int = 2,
        memory_window: int = 10,
    ) -> None:
        self._llm = llm
        self._policy = policy
        self._max_steps = max_steps
        self._enable_planning = enable_planning
        self._planning_threshold = planning_threshold
        self._memory_window = memory_window

        self._registry = ToolRegistry()
        self._registry.register(ReadFileTool())
        self._registry.register(WriteFileTool())
        self._registry.register(ListDirTool())
        self._registry.register(BashTool())

        self._executor = Executor(self._registry)
        self._parser = ActionParser()
        self._planner = Planner(llm)

    @classmethod
    def from_config(cls, config_dir: str) -> SimpleAgent:
        config_path = Path(config_dir)

        model_cfg = cls._load_yaml(config_path / "model.yaml")
        agent_cfg = cls._load_yaml(config_path / "agent.yaml")

        llm = ZhipuClient(
            model=model_cfg.get("model_name", "glm-4.7"),
            temperature=model_cfg.get("temperature", 0.7),
            max_tokens=model_cfg.get("max_tokens", 4096),
            timeout=model_cfg.get("timeout", 60),
        )

        policy = PolicyChecker(str(config_path / "policy.yaml"))

        return cls(
            llm=llm,
            policy=policy,
            max_steps=agent_cfg.get("max_steps", 20),
            enable_planning=agent_cfg.get("enable_planning", True),
            planning_threshold=agent_cfg.get("planning_threshold", 2),
            memory_window=agent_cfg.get("memory_window", 10),
        )

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def run(self, task: str) -> str:
        logger.info("Starting task: %s", task)

        state_mgr = StateManager(task, max_steps=self._max_steps)
        memory = Memory(window=self._memory_window)
        parser = self._parser

        memory.add("user", task)

        # --- Planning phase ---
        plan = None
        if self._enable_planning and self._planner.needs_planning(task):
            state_mgr.transition("planning")
            plan = self._planner.generate_plan(task)
            state_mgr.set_plan(plan)
            memory.add("system", f"Plan: {plan.summary or plan.goal}")
            logger.info("Plan generated: %d steps", len(plan.steps))

        # --- Execution loop ---
        state_mgr.transition("running")

        while not state_mgr.is_terminal() and not state_mgr.over_step_limit():
            state_mgr.increment_step()

            # Determine current step
            current_step = None
            if plan:
                current_step = self._next_pending_step(plan)
                if current_step is None:
                    # All steps done
                    break
                state_mgr.set_current_step(current_step.id)

            # Build prompt
            prompt = build_action_prompt(
                user_request=task,
                tool_descriptions=self._registry.tool_descriptions_for_prompt(),
                memory_context=memory.compact_context(),
                plan_summary=plan.summary if plan else None,
                current_step=f"{current_step.title}: {current_step.description}" if current_step else None,
            )

            # Get action from LLM
            llm_output = self._llm.generate(prompt)
            action = parser.safe_parse(llm_output)

            if action is None:
                memory.add("system", "Warning: Failed to parse LLM output, retrying")
                logger.warning("Parse failed on step %d", state_mgr.state.step_count)
                continue

            # Handle action types
            if action.type == "finish":
                memory.add("agent", f"Finish: {action.message}")
                break

            elif action.type == "ask_user":
                logger.info("Agent asks: %s", action.message)
                # In v1, we treat ask_user as a signal to finish with the question
                memory.add("agent", f"Asks user: {action.message}")
                return f"[Agent asks]: {action.message}"

            elif action.type == "replan":
                if plan:
                    step_id = state_mgr.state.current_step_id or "1"
                    reason = action.reason or "Agent requested replan"
                    plan = self._planner.replan(task, plan, step_id, reason)
                    state_mgr.set_plan(plan)
                    memory.add("system", f"Replanned: {plan.summary or plan.goal}")
                    logger.info("Replanned: %d steps", len(plan.steps))
                continue

            elif action.type == "tool_call":
                # Policy check
                decision = self._policy.check(action)
                if not decision.allowed:
                    memory.add("system", f"Policy blocked: {decision.reason}")
                    logger.warning("Policy blocked: %s", decision.reason)
                    continue
                if decision.requires_approval:
                    logger.info("Approval required for: %s", action.tool)
                    # In v1, auto-approve for now (can add interactive approval later)
                    memory.add("system", f"Auto-approved: {action.tool}")

                # Execute
                result = self._executor.execute(action)
                result_str = result.output if result.success else f"Error: {result.error}"
                memory.add("tool", f"{action.tool}({action.args}) -> {result_str}")

                # Update plan step
                if plan and current_step:
                    current_step.status = "done" if result.success else "failed"
                    current_step.notes = result_str[:200]

                logger.info(
                    "Step %d: %s(%s) -> %s",
                    state_mgr.state.step_count,
                    action.tool,
                    action.args,
                    result_str[:100],
                )

        # --- Verification ---
        logger.info("Verifying task completion...")
        state_mgr.transition("verifying")
        actions_summary = memory.compact_context()
        verify_prompt = build_verify_prompt(task, actions_summary)
        verify_output = self._llm.generate(verify_prompt)
        verify_data = extract_json_from_text(verify_output)

        if isinstance(verify_data, dict):
            complete = verify_data.get("complete", True)
            logger.info("Verification result: complete=%s", complete)
            if not complete:
                missing = verify_data.get("missing", "unknown")
                logger.warning("Verification found incomplete: %s", missing)
                memory.add("system", f"Verification note: {missing}")
        else:
            logger.warning("Verification output could not be parsed")

        # --- Summary ---
        logger.info("Generating final summary...")
        summary_prompt = build_summary_prompt(task, actions_summary)
        summary_output = self._llm.generate(summary_prompt)
        summary_data = extract_json_from_text(summary_output)

        if isinstance(summary_data, dict):
            state_mgr.transition("completed")
            summary = summary_data.get("summary", summary_output)
            logger.info("Task completed. Summary: %s", summary)
            return summary

        state_mgr.transition("completed")
        logger.info("Task completed. Summary: %s", summary_output)
        return summary_output

    def _next_pending_step(self, plan):
        for step in plan.steps:
            if step.status == "pending":
                return step
        return None
