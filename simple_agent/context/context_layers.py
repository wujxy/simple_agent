from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptContext:
    # New structured blocks
    project_rules_block: str = ""
    objective_block: str = ""
    execution_state: str = ""
    working_set_block: str = ""
    artifact_snapshot: str = ""
    next_decision_point: str = ""
    prompt_memory_block: str = ""

    def to_dict(self) -> dict:
        return {
            "project_rules_block": self.project_rules_block,
            "objective_block": self.objective_block,
            "execution_state": self.execution_state,
            "working_set_block": self.working_set_block,
            "artifact_snapshot": self.artifact_snapshot,
            "next_decision_point": self.next_decision_point,
            "prompt_memory_block": self.prompt_memory_block,
        }
