from simple_agent.tools.core.types import ToolCapabilities, ToolSpec

GlobSpec = ToolSpec(
    name="glob",
    description="Find files matching a glob pattern",
    family="filesystem",
    capabilities=ToolCapabilities(read_only=True, idempotent=True),
    input_schema={
        "pattern": "string (required) - glob pattern, e.g. '**/*.py'",
        "root": "string (optional, default '.') - directory to search under",
        "max_results": "int (optional, default 200) - maximum matches returned",
    },
    output_schema={
        "matches": "list[string] - matched paths",
        "truncated": "bool - whether matches were truncated",
    },
    guarantees=["returns sorted matching paths within root"],
    short_prompt="glob(pattern, root?, max_results?)",
)
