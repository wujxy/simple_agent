from __future__ import annotations

from simple_agent.hooks.pre_tool_use import HookDecision, PreToolUseHook, ToolInvocation


class HookManager:
    def __init__(self, pre_tool_hooks: list[PreToolUseHook]) -> None:
        self._hooks = pre_tool_hooks

    async def run_pre_tool_use(self, invocation: ToolInvocation) -> HookDecision:
        for hook in self._hooks:
            decision = await hook.before_tool_use(invocation)
            if decision.status != "allow":
                return decision
        return HookDecision(status="allow")
