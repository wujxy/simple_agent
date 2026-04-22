# Simple Agent Tools Introduction

This document provides an overview of the tools available in the `simple_agent` project.

## Tool Architecture

All tools in the `simple_agent` framework follow a consistent architecture:

- **BaseTool**: Base class that all tools inherit from (`simple_agent/tools/core/base.py`)
- **ToolObservation**: Structured return type with fields:
  - `ok`: Boolean indicating success
  - `status`: One of `success`, `noop`, `unchanged`, `error`, `approval_required`, `context_required`
  - `summary`: Brief description of the result
  - `facts`: List of key facts about the operation
  - `data`: Additional data returned by the tool
  - `error`: Error message if the operation failed
- **Registry**: Central registry for managing available tools (`simple_agent/tools/core/registry.py`)

## Available Tools

### 1. Bash Tool

**Location**: `simple_agent/tools/bash/`

**Purpose**: Execute shell commands asynchronously with timeout support.

**Features**:
- Runs commands via `asyncio.create_subprocess_shell`
- Configurable timeout (default 30s, max 300s)
- Captures both stdout and stderr
- Returns exit code, stdout, and stderr
- Handles timeout errors gracefully

**Input Parameters**:
- `command` (required): The shell command to execute
- `timeout` (optional): Command timeout in seconds

**Return Values**:
- On success: `ok=True`, `status="success"`, exit code 0, stdout/stderr content
- On timeout: `ok=False`, `status="error"`, retryable=True
- On error: `ok=False`, `status="error"` with error message

### 2. List Directory Tool

**Location**: `simple_agent/tools/list_dir/`

**Purpose**: List files and directories in a given path.

**Features**:
- Returns sorted list of directory entries
- Handles empty directories
- Error handling for non-existent paths and non-directory paths

**Input Parameters**:
- `path` (required): Directory path to list

**Return Values**:
- On success: `ok=True`, `status="success"`, sorted list of entries
- Empty directory: Returns success with empty entries list
- On error: `ok=False`, `status="error"` with descriptive error message

### 3. Read File Tool

**Location**: `simple_agent/tools/read_file/`

**Purpose**: Read text content from a file.

**Features**:
- Read-only operation
- Supports optional line range (start_line, max_lines)
- Returns status="unchanged" if same range was already read and file hasn't changed
- Guarantees original content preservation on success

**Input Parameters**:
- `path` (required): Absolute file path to read
- `start_line` (optional): First line to read (default: 1)
- `max_lines` (optional): Maximum lines to return

**Return Values**:
- On success: `ok=True`, file content in `data.content`
- On unchanged: `ok=True`, `status="unchanged"` (use cached knowledge)
- On error: `ok=False`, `status="error"` with error details

### 4. Write File Tool

**Location**: `simple_agent/tools/write_file/`

**Purpose**: Write content to a text file.

**Features**:
- Requires approval before execution
- Returns status="noop" if file already contains identical content
- On success, guarantees file content exactly matches supplied content
- Returns changed_paths with the modified file path

**Input Parameters**:
- `path` (required): File path to write
- `content` (required): Content to write to the file

**Return Values**:
- On success: `ok=True`, `status="success"`, changed_paths contains [path]
- On noop: `ok=True`, `status="noop"` (file already had identical content)
- On error: `ok=False`, `status="error"` with error details

## Tool Usage Guidelines

### Trust Rules

- **write_file success**: The file now exactly matches the content supplied. Do NOT re-read it.
- **write_file noop**: The file already had identical content. No action was needed.
- **read_file success**: `data.content` is the file text. Trust it.
- **read_file unchanged**: The file has not changed since last read. Use cached knowledge.
- **bash success**: Exit code 0, stdout/stderr contain full output.
- **bash error**: Check exit code and stderr for the failure reason.

### Best Practices

1. **After a successful write**: Prefer bash (run tests) or verify over re-reading the file.
2. **Avoid duplicate calls**: Do NOT issue the same tool call with identical arguments twice without new evidence.
3. **Prefer finishing**: Once all subgoals are met, use finish rather than perfecting.
4. **Verification**: If verification fails, analyze the error output and make targeted fixes.

## Status Codes Reference

| Status | Description |
|--------|-------------|
| `success` | The operation completed successfully |
| `noop` | The operation was skipped because it would have no effect |
| `unchanged` | The resource has not changed since the last read |
| `error` | The operation failed |
| `approval_required` | User approval is needed before proceeding |
| `context_required` | Insufficient context to justify the action |

## Extending the Toolset

To add a new tool:

1. Create a new directory under `simple_agent/tools/`
2. Create a `tool.py` file that inherits from `BaseTool`
3. Define the tool's `spec` and `input_model`
4. Implement the `async run()` method that returns a `ToolObservation`
5. Register the tool in the registry if needed

## Core Components

- **BaseTool**: `simple_agent/tools/core/base.py` - Abstract base class for all tools
- **ToolObservation**: `simple_agent/tools/core/types.py` - Structured observation type
- **Registry**: `simple_agent/tools/core/registry.py` - Tool registration and discovery

---

For more details, refer to the source code in the `simple_agent/tools/` directory.