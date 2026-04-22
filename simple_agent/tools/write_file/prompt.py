WRITE_FILE_PROMPT = """Tool: write_file
- Purpose: Write content to a file, creating it or overwriting it entirely.
- Input: path (required), content (required).
- Output: On success, the file content exactly matches the content argument.
- Guarantees: The file content is guaranteed to match what you passed. Do NOT re-read the file to verify — trust the guarantee.
- Noop: If the file already has identical content, returns noop (no write performed).
- Trust rule: After a successful write_file, you already know the file content. Do NOT read it back.
"""
