from __future__ import annotations

from simple_agent.memory.compact_service import CompactService
from simple_agent.memory.memory_store import MemoryStore
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("memory_service")


class MemoryService:
    """Budget-aware prompt memory manager."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        compact_service: CompactService | None = None,
    ) -> None:
        self._store = store
        self._compact = compact_service
        self._next_id = 0

    async def record_user_message(
        self, session_id: str, text: str, *, step: int | None = None,
    ) -> None:
        self._store.add(session_id, self._new_item(
            kind="user",
            role="user",
            created_at_step=step,
            content=text,
            summary=text,
        ))

    async def record_tool_result(
        self,
        session_id: str,
        turn_id: str,
        result: dict,
        *,
        step: int | None = None,
    ) -> None:
        error = result.get("error")
        errors = self._as_list(result.get("errors"))
        if error:
            errors.append(str(error))

        self._store.add(session_id, self._new_item(
            kind="tool",
            role="tool",
            created_at_step=step,
            turn_id=turn_id,
            tool_name=result.get("tool_name", "unknown"),
            path=self._extract_path(result),
            ok=result.get("ok", False),
            status=result.get("status", "success"),
            summary=result.get("summary", ""),
            facts=self._as_list(result.get("facts")),
            data=result.get("data", {}),
            error=error,
            errors=errors,
            changed_paths=self._as_list(result.get("changed_paths")),
        ))

    async def add_system_note(
        self, session_id: str, note: str, *, step: int | None = None,
    ) -> None:
        self._store.add(session_id, self._new_item(
            kind="system",
            role="system",
            created_at_step=step,
            content=note,
            summary=note,
        ))

    async def record_step_event(self, session_id: str, payload: dict) -> None:
        step = payload.get("step")
        self._store.add(session_id, self._new_item(
            kind="step",
            role="step",
            created_at_step=step,
            action_type=payload.get("action_type", ""),
            tool_name=payload.get("tool_name", ""),
            args=payload.get("args", {}),
            ok=payload.get("ok", True),
            summary=payload.get("summary", ""),
            facts=self._as_list(payload.get("facts")),
            changed_paths=self._as_list(payload.get("changed_paths")),
            errors=self._as_list(payload.get("errors")),
            verification=self._as_list(payload.get("verification")),
        ))

    async def record_verify_result(self, session_id: str, payload: dict) -> None:
        step = payload.get("step")
        complete = payload.get("complete", True)
        missing = payload.get("missing")
        summary = "Verification passed" if complete else f"Verification incomplete: {missing or 'unknown'}"
        verification = [payload.get("reason") or summary]
        if missing:
            verification.append(f"missing: {missing}")
        self._store.add(session_id, self._new_item(
            kind="verify",
            role="verify",
            created_at_step=step,
            ok=complete,
            summary=summary,
            content=summary,
            verification=verification,
            errors=[] if complete else [str(missing or "verification incomplete")],
        ))

    async def get_recent(self, session_id: str, limit: int = 10) -> list[dict]:
        return self._store.get_recent(session_id, limit)

    async def build_prompt_memory(self, session_id: str, *, current_step: int) -> str:
        items = self._store.get_all(session_id)
        if self._compact and items:
            result = await self._compact.maybe_compact(items, current_step=current_step)
            if result.get("did_compact"):
                items = result["new_items"]
                self._store.replace_all(session_id, items)
        return self._render_memory_items(items)

    def _new_item(
        self,
        *,
        kind: str,
        created_at_step: int | None = None,
        priority: str = "normal",
        **fields,
    ) -> dict:
        step = int(created_at_step or 0)
        self._next_id += 1
        item = {
            "id": f"mem_{kind}_{step}_{self._next_id}",
            "kind": kind,
            "state": "hot",
            "priority": priority,
            "created_at_step": step,
            "content": "",
            "summary": "",
            "facts": [],
            "changed_paths": [],
            "errors": [],
            "decisions": [],
            "verification": [],
        }
        item.update(fields)
        for key in ("facts", "changed_paths", "errors", "decisions", "verification"):
            item[key] = self._as_list(item.get(key))
        return item

    def _render_memory_items(self, items: list[dict]) -> str:
        if not items:
            return "(no prior context)"

        lines: list[str] = []
        for item in items:
            kind = item.get("kind", item.get("role", "unknown"))
            state = item.get("state", "hot")

            if state == "compacted" and kind == "summary":
                lines.append("[compacted summary]")
                self._append_indented(lines, item.get("content") or item.get("summary"))
                continue

            summary = item.get("summary") or item.get("content") or ""
            ok = item.get("ok")

            if kind == "step":
                ok_label = "ok" if ok else "FAILED"
                step = item.get("created_at_step", "")
                action_type = item.get("action_type", "")
                tool_name = item.get("tool_name", "")
                lines.append(f"[step {step}] {action_type} -> {tool_name}({ok_label})")
                self._append_indented(lines, summary)
            elif kind == "tool":
                ok_label = "ok" if ok else "FAILED"
                tool_name = item.get("tool_name", "")
                lines.append(f"[tool] {tool_name}({ok_label}): {summary}")
                if item.get("path"):
                    lines.append(f"  path: {item['path']}")
            elif kind == "verify":
                lines.append(f"[verify] {summary}")
            elif kind in ("user", "system"):
                content = item.get("content") or summary
                lines.append(f"[{kind}] {str(content)[:300]}")
            else:
                role = item.get("role", kind)
                if summary:
                    lines.append(f"[{role}] {str(summary)[:300]}")

            for fact in item.get("facts", [])[:5]:
                lines.append(f"  fact: {fact}")
            for path in item.get("changed_paths", [])[:8]:
                lines.append(f"  modified: {path}")
            for error in item.get("errors", [])[:3]:
                lines.append(f"  error: {str(error)[:200]}")
            for verify in item.get("verification", [])[:3]:
                lines.append(f"  verification: {verify}")

        return "\n".join(lines)

    def _append_indented(self, lines: list[str], text: object) -> None:
        if not text:
            return
        for line in str(text).splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(f"  {stripped}")

    def _as_list(self, value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        return [value]

    def _extract_path(self, result: dict) -> str:
        data = result.get("data", {})
        if isinstance(data, dict) and data.get("path"):
            return str(data["path"])
        args = result.get("args", {})
        if isinstance(args, dict) and args.get("path"):
            return str(args["path"])
        changed = result.get("changed_paths", [])
        if changed:
            return str(changed[0])
        return ""
