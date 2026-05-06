from simple_agent.tools.core.types import ToolCapabilities, ToolSpec

MultiEditSpec = ToolSpec(
    name="multi_edit",
    description="Apply multiple exact text replacements to one file",
    family="filesystem",
    capabilities=ToolCapabilities(mutates_files=True, requires_approval=True),
    input_schema={
        "path": "string (required) - file to edit",
        "edits": "list[object] - old_text, new_text, replace_all",
    },
    output_schema={
        "edits_applied": "int",
        "replacements": "int",
    },
    guarantees=["edits are applied in order; if validation fails, no write is performed"],
    short_prompt="multi_edit(path, edits)",
)
