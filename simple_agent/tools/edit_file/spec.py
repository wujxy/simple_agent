from simple_agent.tools.core.types import ToolCapabilities, ToolSpec

EditFileSpec = ToolSpec(
    name="edit_file",
    description="Replace exact text in a file",
    family="filesystem",
    capabilities=ToolCapabilities(mutates_files=True, requires_approval=True),
    input_schema={
        "path": "string (required) - file to edit",
        "old_text": "string (required) - exact text to replace",
        "new_text": "string (required) - replacement text",
        "replace_all": "bool (optional, default false) - replace every occurrence",
    },
    output_schema={
        "replacements": "int - number of replacements applied",
        "lines_added": "int",
        "lines_removed": "int",
    },
    guarantees=["on success, changed_paths contains the edited path"],
    short_prompt="edit_file(path, old_text, new_text, replace_all?)",
)
