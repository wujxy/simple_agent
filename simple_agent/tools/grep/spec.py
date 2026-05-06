from simple_agent.tools.core.types import ToolCapabilities, ToolSpec

GrepSpec = ToolSpec(
    name="grep",
    description="Search text files for a pattern and return matching lines",
    family="filesystem",
    capabilities=ToolCapabilities(read_only=True, idempotent=True),
    input_schema={
        "pattern": "string (required) - literal text to search for",
        "root": "string (optional, default '.') - directory to search under",
        "include": "string (optional, default '**/*') - glob for files to search",
        "max_results": "int (optional, default 100) - maximum matches returned",
        "case_sensitive": "bool (optional, default true)",
    },
    output_schema={
        "matches": "list[object] - path, line_number, line",
        "match_count": "int - total matches found before truncation",
        "truncated": "bool",
    },
    guarantees=["returns line numbers for each returned match"],
    short_prompt="grep(pattern, root?, include?, max_results?, case_sensitive?)",
)
