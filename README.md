# simple_agent

A clean, minimal AI agent framework in Python. Built on a structured plan → act → observe → reflect → verify → finish loop.

## Project Structure

```
simple_agent/
├── pyproject.toml
├── configs/
│   ├── agent.yaml        # agent behavior settings
│   ├── model.yaml        # LLM provider config
│   └── policy.yaml       # permission rules
├── simple_agent/
│   ├── agent.py           # main orchestrator
│   ├── planner.py         # plan generation & replanning
│   ├── executor.py        # single-action executor
│   ├── parser.py          # LLM output → typed action
│   ├── policy.py          # permission & safety checks
│   ├── memory.py          # short-term runtime memory
│   ├── state.py           # run state management
│   ├── schemas.py         # Pydantic data models
│   ├── llm/
│   │   ├── base.py        # abstract LLM interface
│   │   └── zhipu_client.py
│   ├── prompts/
│   │   ├── planner_prompt.py
│   │   ├── action_prompt.py
│   │   ├── verify_prompt.py
│   │   └── summary_prompt.py
│   ├── tools/
│   │   ├── base.py        # tool interface & spec
│   │   ├── registry.py    # tool registration & lookup
│   │   ├── file_tools.py  # read, write, list
│   │   └── bash_tools.py  # shell execution
│   └── utils/
│       ├── json_utils.py
│       └── logging_utils.py
└── tests/
    ├── test_agent.py
    ├── test_planner.py
    ├── test_parser.py
    ├── test_tools.py
    ├── test_memory.py
    └── test_policy.py
```

## Install

```bash
pip install -e ".[dev]"
```

## Configuration

Set your ZhipuAI API key as an environment variable:

```bash
export ZHIPU_API_KEY="your-api-key-here"
```

Edit config files in `configs/` to customize:
- **agent.yaml** — max steps, planning toggle, memory window
- **model.yaml** — model name, temperature, token limit
- **policy.yaml** — which tools are allowed, which need approval

## Usage

```python
from simple_agent.agent import SimpleAgent

agent = SimpleAgent.from_config("configs")
result = agent.run("Read README.md and summarize the project")
print(result)
```

## Policy & Approval

Tools are gated by policy rules:
- **Allowed without approval**: read_file, list_dir
- **Requires approval**: write_file, bash (auto-approved in v1)
- **Blocked**: destructive commands (rm -rf, mkfs, etc.)

Configure in `configs/policy.yaml`.

## Run Tests

```bash
pytest tests/ -v
```

Tests use mocked LLM outputs — no API key required.
