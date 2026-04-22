from simple_agent.tools.core.types import ToolCapabilities, ToolSpec

WriteFileSpec = ToolSpec(
    name="write_file",
    description="Write content to a text file",
    family="filesystem",
    capabilities=ToolCapabilities(
        read_only=False,
        idempotent=False,
        mutates_files=True,
        requires_approval=True,
        preferred_after_write=False,
    ),
    input_schema={
        "path": "string (required) — file path to write",
        "content": "string (required) — content to write",
    },
    output_schema={
        "operation": "string — 'created' | 'updated' | 'noop'",
        "lines_written": "int",
        "lines_added": "int",
        "lines_removed": "int",
    },
    guarantees=[
        "on success, the file content exactly matches the content argument",
        "returns status='noop' if the file already contains identical content",
        "on success, changed_paths contains [path]",
    ],
    short_prompt="write_file(path, content)",
    detail_prompt=(
        "Purpose: write content to a file.\n"
        "Returns: success / noop / error.\n"
        "Guarantee: on success, the file content exactly matches your content argument.\n"
        "If the file already has identical content, returns noop (no write performed).\n"
        "This tool creates parent directories automatically."
    ),
)
