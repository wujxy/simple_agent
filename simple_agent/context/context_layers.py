from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptContext:
    # New structured blocks
    objective_block: str = ""
    execution_state: str = ""
    artifact_snapshot: str = ""
    next_decision_point: str = ""
    prompt_memory_block: str = ""

    def to_dict(self) -> dict:
        return {
            "objective_block": self.objective_block,
            "execution_state": self.execution_state,
            "artifact_snapshot": self.artifact_snapshot,
            "next_decision_point": self.next_decision_point,
            "prompt_memory_block": self.prompt_memory_block,
        }
