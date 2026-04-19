from __future__ import annotations

from pathlib import Path

import yaml


def load_config(config_dir: str | None = None) -> dict:
    config: dict = {
        "runtime": {
            "max_steps": 20,
        },
        "model": {
            "provider": "zhipu",
            "model_name": "glm-4.7",
            "temperature": 0.0,
            "max_tokens": 4096,
            "timeout": 60,
        },
        "policy": {
            "allow_read": True,
            "allow_write": False,
            "allow_bash": False,
            "require_approval_for_write": True,
            "require_approval_for_bash": True,
            "blocked_commands": ["rm -rf", "mkfs", "dd", "format"],
        },
        "context": {
            "recent_history_limit": 20,
            "memory_limit": 10,
            "max_tool_output_chars": 2000,
        },
    }

    if config_dir:
        config_path = Path(config_dir)
        config["model"].update(_load_yaml(config_path / "model.yaml"))
        agent_cfg = _load_yaml(config_path / "agent.yaml")
        config["runtime"].update({
            "max_steps": agent_cfg.get("max_steps", 20),
        })
        config["policy_path"] = str(config_path / "policy.yaml")

    return config


def _load_yaml(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}
