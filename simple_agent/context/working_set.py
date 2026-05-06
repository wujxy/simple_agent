from __future__ import annotations

from pydantic import BaseModel, Field


class FileWorkingSetItem(BaseModel):
    path: str
    content: str = ""
    start_line: int = 1
    end_line: int = 0
    total_lines: int = 0
    truncated: bool = False
    content_hash: str = ""
    last_updated_step: int = 0
    stale: bool = False


class GrepHit(BaseModel):
    path: str
    line_number: int
    line: str


class WorkingSetState(BaseModel):
    files: dict[str, FileWorkingSetItem] = Field(default_factory=dict)
    grep_hits: list[GrepHit] = Field(default_factory=list)
    modified_paths: list[str] = Field(default_factory=list)
    recent_failures: list[str] = Field(default_factory=list)
    recent_verification: list[str] = Field(default_factory=list)

    def update_from_read(
        self,
        *,
        path: str,
        content: str,
        start_line: int,
        end_line: int,
        total_lines: int,
        truncated: bool,
        content_hash: str,
        step: int,
    ) -> None:
        self.files[path] = FileWorkingSetItem(
            path=path,
            content=content,
            start_line=start_line,
            end_line=end_line,
            total_lines=total_lines,
            truncated=truncated,
            content_hash=content_hash,
            last_updated_step=step,
        )

    def update_from_write(self, *, path: str, step: int) -> None:
        item = self.files.get(path)
        if item:
            item.stale = True
            item.content = ""
            item.last_updated_step = step
        if path not in self.modified_paths:
            self.modified_paths.append(path)

    def update_from_grep(self, hits: list[dict], *, step: int) -> None:
        for hit in hits:
            path = str(hit.get("path", ""))
            line_number = int(hit.get("line_number", 0) or 0)
            line = str(hit.get("line", ""))
            if path and line_number:
                self.grep_hits.append(GrepHit(path=path, line_number=line_number, line=line))
        self.grep_hits = self.grep_hits[-40:]

    def update_from_bash(self, *, command: str, exit_code: int, stderr: str, step: int) -> None:
        if exit_code != 0:
            detail = stderr.strip()[:500] or f"Command failed with exit code {exit_code}"
            self.recent_failures.append(f"$ {command} -> exit {exit_code}: {detail}")
            self.recent_failures = self.recent_failures[-5:]

    def update_from_verification(self, text: str) -> None:
        if text:
            self.recent_verification.append(text[:500])
            self.recent_verification = self.recent_verification[-5:]

    def project(
        self,
        *,
        file_budget: int = 4,
        max_chars_per_file: int = 3000,
        grep_budget: int = 20,
    ) -> str:
        parts: list[str] = []

        active_files = [f for f in self.files.values() if not f.stale and f.content]
        active_files.sort(key=lambda f: f.last_updated_step, reverse=True)
        if active_files:
            file_parts: list[str] = ["Working files:"]
            for item in active_files[:file_budget]:
                content = item.content[:max_chars_per_file]
                truncated_note = "yes" if item.truncated or len(item.content) > max_chars_per_file else "no"
                file_parts.append(
                    f"[{item.path}] lines {item.start_line}-{item.end_line} "
                    f"of {item.total_lines}, hash={item.content_hash}, truncated={truncated_note}\n"
                    f"{content}"
                )
            parts.append("\n\n".join(file_parts))

        if self.grep_hits:
            lines = ["Recent grep hits:"]
            for hit in self.grep_hits[-grep_budget:]:
                lines.append(f"- {hit.path}:{hit.line_number}: {hit.line}")
            parts.append("\n".join(lines))

        if self.modified_paths:
            lines = ["Modified paths:"]
            for path in self.modified_paths[-10:]:
                lines.append(f"- {path}")
            parts.append("\n".join(lines))

        if self.recent_failures:
            lines = ["Recent failures:"]
            for failure in self.recent_failures[-5:]:
                lines.append(f"- {failure}")
            parts.append("\n".join(lines))

        if self.recent_verification:
            lines = ["Recent verification:"]
            for item in self.recent_verification[-5:]:
                lines.append(f"- {item}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)
