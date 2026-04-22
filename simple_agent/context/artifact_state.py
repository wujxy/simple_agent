from __future__ import annotations

from pydantic import BaseModel, Field


class FileArtifact(BaseModel):
    path: str
    exists: bool = True
    snapshot: str = ""
    snapshot_full_len: int = 0
    last_write_exact_match: bool = False
    last_write_operation: str = ""  # created / updated / noop
    last_updated_step: int = 0
    stale: bool = False  # invalidated by later write


class ShellArtifact(BaseModel):
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class ArtifactState(BaseModel):
    files: dict[str, FileArtifact] = {}
    shell_results: list[ShellArtifact] = Field(default_factory=list)
    write_guarantees: list[dict] = Field(default_factory=list)
    _consecutive_no_advance: int = 0

    def update_from_read(self, path: str, content: str, step: int) -> None:
        fa = self.files.get(path)
        if fa is None:
            fa = FileArtifact(path=path, exists=True)
            self.files[path] = fa
        fa.snapshot = content
        fa.snapshot_full_len = len(content)
        fa.exists = True
        fa.last_updated_step = step

    def update_from_write(self, path: str, operation: str, step: int) -> None:
        # Invalidate old snapshots for this file
        fa = self.files.get(path)
        if fa is not None:
            fa.stale = True
            fa.snapshot = ""

        fa = FileArtifact(
            path=path,
            exists=True,
            last_write_exact_match=True,
            last_write_operation=operation,
            last_updated_step=step,
        )
        self.files[path] = fa

        self.write_guarantees = [
            g for g in self.write_guarantees if g.get("path") != path
        ]
        self.write_guarantees.append({
            "path": path,
            "operation": operation,
            "guarantee": f"File '{path}' now exactly matches the last supplied content ({operation}).",
        })

    def update_from_bash(self, command: str, exit_code: int, stdout: str, stderr: str) -> None:
        self.shell_results.append(ShellArtifact(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        ))

    def get_active_files(self) -> list[FileArtifact]:
        return [f for f in self.files.values() if f.exists and not f.stale]

    def project_snapshots(self, budget: int = 2, max_chars: int = 1500) -> str:
        """Project the most relevant file snapshots within budget."""
        candidates = [
            f for f in self.files.values()
            if f.exists and f.snapshot and not f.stale
        ]
        if not candidates:
            return ""

        # Sort by recency
        candidates.sort(key=lambda f: f.last_updated_step, reverse=True)
        selected = candidates[:budget]

        parts: list[str] = []
        for fa in selected:
            content = fa.snapshot[:max_chars]
            truncated_note = ""
            if fa.snapshot_full_len > max_chars:
                truncated_note = f" ({fa.snapshot_full_len} chars total, showing first {max_chars})"
            parts.append(f"[{fa.path}]{truncated_note}:\n{content}")

        return "\n\n".join(parts)

    def project_latest_shell(self, max_stdout: int = 1000, max_stderr: int = 800) -> str:
        """Project the most recent shell result."""
        if not self.shell_results:
            return ""
        latest = self.shell_results[-1]
        parts = [f"$ {latest.command} -> exit {latest.exit_code}"]
        if latest.stdout:
            parts.append(f"stdout: {latest.stdout[:max_stdout]}")
        if latest.stderr:
            parts.append(f"stderr: {latest.stderr[:max_stderr]}")
        return "\n".join(parts)

    def project_write_guarantees(self) -> str:
        """Project write guarantees."""
        if not self.write_guarantees:
            return ""
        lines = [f"- {g['guarantee']}" for g in self.write_guarantees[-3:]]
        return "\n".join(lines)
