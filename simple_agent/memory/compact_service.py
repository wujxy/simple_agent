from __future__ import annotations

from simple_agent.utils.logging_utils import get_logger

logger = get_logger("compact_service")


class CompactService:
    """Rule-based v0 compact service for prompt memory."""

    def __init__(
        self,
        char_budget: int = 12000,
        trigger_ratio: float = 0.8,
        hot_keep_last: int = 8,
        min_candidates: int = 6,
    ) -> None:
        self.char_budget = char_budget
        self.trigger_ratio = trigger_ratio
        self.hot_keep_last = hot_keep_last
        self.min_candidates = min_candidates

    async def maybe_compact(self, items: list[dict], *, current_step: int) -> dict:
        before_size = self._estimate_chars(items)
        threshold = self.char_budget * self.trigger_ratio
        if before_size <= threshold:
            return {
                "did_compact": False,
                "new_items": items,
                "before_size": before_size,
                "after_size": before_size,
                "replaced_count": 0,
                "evicted_count": 0,
            }

        prefix_items, hot_tail = self._split_hot_tail(items)
        candidates = [item for item in prefix_items if item.get("state", "hot") == "hot"]
        if len(candidates) < self.min_candidates:
            return {
                "did_compact": False,
                "new_items": items,
                "before_size": before_size,
                "after_size": before_size,
                "replaced_count": 0,
                "evicted_count": 0,
            }

        summary_payload = self._generate_summary_stub(candidates)
        summary_item = {
            "id": f"mem_summary_{current_step}",
            "kind": "summary",
            "state": "compacted",
            "priority": "normal",
            "created_at_step": current_step,
            "source_range": {
                "from_step": candidates[0].get("created_at_step", 0),
                "to_step": candidates[-1].get("created_at_step", current_step),
            },
            "content": summary_payload,
            "summary": summary_payload,
        }

        kept_prefix = [item for item in prefix_items if item.get("state", "hot") != "hot"]
        new_items = kept_prefix + [summary_item] + hot_tail

        evicted_count = 0
        while self._estimate_chars(new_items) > self.char_budget:
            idx = self._find_oldest_compacted_index(new_items)
            if idx is None:
                break
            del new_items[idx]
            evicted_count += 1

        after_size = self._estimate_chars(new_items)
        logger.info(
            "Compacted memory: %d -> %d items, %d -> %d chars, %d evicted",
            len(items),
            len(new_items),
            before_size,
            after_size,
            evicted_count,
        )
        return {
            "did_compact": True,
            "new_items": new_items,
            "summary_item": summary_item,
            "before_size": before_size,
            "after_size": after_size,
            "replaced_count": len(candidates),
            "evicted_count": evicted_count,
        }

    def _split_hot_tail(self, items: list[dict]) -> tuple[list[dict], list[dict]]:
        if self.hot_keep_last <= 0:
            return list(items), []
        hot_indices = [i for i, item in enumerate(items) if item.get("state", "hot") == "hot"]
        keep_indices = set(hot_indices[-self.hot_keep_last:])
        prefix: list[dict] = []
        tail: list[dict] = []
        for idx, item in enumerate(items):
            if idx in keep_indices:
                tail.append(item)
            else:
                prefix.append(item)
        return prefix, tail

    def _estimate_chars(self, items: list[dict]) -> int:
        total = 0
        for item in items:
            for key in ("content", "summary"):
                total += len(str(item.get(key) or ""))
            for key in ("facts", "errors", "decisions", "verification"):
                value = item.get(key, [])
                if isinstance(value, list):
                    total += sum(len(str(entry)) for entry in value)
                elif value:
                    total += len(str(value))
        return total

    def _find_oldest_compacted_index(self, items: list[dict]) -> int | None:
        for idx, item in enumerate(items):
            if item.get("state") == "compacted":
                return idx
        return None

    def _generate_summary_stub(self, items: list[dict]) -> str:
        completed: list[str] = []
        facts: list[str] = []
        modified: list[str] = []
        verification: list[str] = []
        errors: list[str] = []
        decisions: list[str] = []

        for item in items:
            self._append_unique(completed, item.get("summary") or item.get("content"), limit=10)
            for fact in item.get("facts", []) or []:
                self._append_unique(facts, fact, limit=12)
            for path in item.get("changed_paths", []) or []:
                self._append_unique(modified, path, limit=12)
            for verify in item.get("verification", []) or []:
                self._append_unique(verification, verify, limit=8)
            for error in item.get("errors", []) or []:
                self._append_unique(errors, str(error)[:200], limit=6)
            for decision in item.get("decisions", []) or []:
                self._append_unique(decisions, decision, limit=8)

        parts: list[str] = []
        if completed:
            parts.append("Completed: " + "; ".join(completed))
        if facts:
            parts.append("Facts: " + "; ".join(facts))
        if modified:
            parts.append("Modified: " + "; ".join(modified))
        if verification:
            parts.append("Verification: " + "; ".join(verification))
        if errors:
            parts.append("Errors: " + "; ".join(errors))
        if decisions:
            parts.append("Decisions: " + "; ".join(decisions))
        return "\n".join(parts) if parts else "(compacted memory, no extractable content)"

    def _append_unique(self, values: list[str], value: object, *, limit: int) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text or text in values or len(values) >= limit:
            return
        values.append(text)

    async def _generate_summary_via_llm(self, items: list[dict]) -> str:
        raise NotImplementedError("LLM-based compact is not implemented in Phase 1")
