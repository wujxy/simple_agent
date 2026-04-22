READ_FILE_PROMPT = """Tool: read_file
- Purpose: Read text content from a file.
- Input: path (required), start_line (optional, default 1), max_lines (optional).
- Output: On success, data.content contains the file text.
- Guarantees: The returned content is an exact slice of the file. No modification is made.
- Trust rule: If read_file returns success, you have the file content. Do NOT re-read the same file unless you have reason to believe it changed (e.g., after a write_file or bash command that modifies it).
"""
