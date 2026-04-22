from simple_agent.tools.core.types import ToolCapabilities, ToolSpec

ListDirSpec = ToolSpec(
    name="list_dir",
    description="List files and directories in a given path",
    family="filesystem",
    capabilities=ToolCapabilities(
        read_only=True,
        idempotent=True,
    ),
    input_schema={
        "path": "string (required) — directory path to list",
    },
    output_schema={
        "entries": "list[string] — sorted entry names",
    },
    guarantees=[
        "returns sorted list of all entries in the directory",
        "returns empty list if directory is empty",
    ],
    short_prompt="list_dir(path)",
    detail_prompt=(
        "Purpose: list directory contents.\n"
        "Returns: success / error.\n"
        "Guarantee: data.entries contains sorted names of all files and directories."
    ),
)
