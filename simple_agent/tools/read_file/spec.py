from simple_agent.tools.core.types import ToolCapabilities, ToolSpec

ReadFileSpec = ToolSpec(
    name="read_file",
    description="Read text from a file",
    family="filesystem",
    capabilities=ToolCapabilities(
        read_only=True,
        idempotent=True,
        returns_high_value_payload=True,
    ),
    input_schema={
        "path": "string (required) — absolute file path",
        "start_line": "int (optional, default 1) — first line to read",
        "max_lines": "int (optional) — max lines to return",
    },
    output_schema={
        "content": "string | None — file content (may be sliced)",
        "total_lines": "int — total lines in file",
        "truncated": "bool — whether output was truncated",
    },
    guarantees=[
        "on success, the original content is preserved in data.content",
        "returns status='unchanged' if the same range was already read and file has not changed",
    ],
    short_prompt="read_file(path, start_line?, max_lines?)",
    detail_prompt=(
        "Purpose: read text from a file.\n"
        "Returns: success / unchanged / error.\n"
        "Guarantee: on success, content is in data.content.\n"
        "If the same range was already read and the file has not changed, returns unchanged."
    ),
)
