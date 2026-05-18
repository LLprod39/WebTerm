from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitOpsError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitStatus:
    branch: str
    short_status: str

    @property
    def is_dirty(self) -> bool:
        return bool(self.short_status.strip())

    def render(self) -> str:
        status = self.short_status.strip() or "clean"
        return f"Branch: {self.branch}\nStatus:\n{status}"


class GitOps:
    def __init__(self, project_root: Path, *, branch_prefix: str = "codex/", remote: str = "origin") -> None:
        self.project_root = project_root.resolve()
        self.branch_prefix = branch_prefix
        self.remote = remote

    def status(self) -> GitStatus:
        branch = self._run(["git", "branch", "--show-current"]).strip() or "(detached)"
        short_status = self._run(["git", "status", "--short"]).strip()
        return GitStatus(branch=branch, short_status=short_status)

    def create_branch_for_task(self, task_id: int, title: str) -> str:
        slug = self._slugify(title)
        branch = f"{self.branch_prefix}task-{task_id}-{slug}"[:80].rstrip("-/")
        existing = self._run(["git", "branch", "--list", branch]).strip()
        if existing:
            self._run(["git", "switch", branch])
            return branch
        self._run(["git", "switch", "-c", branch])
        return branch

    def commit_all(self, message: str) -> str:
        if not self.status().is_dirty:
            raise GitOpsError("Nothing to commit.")
        self._run(["git", "add", "-A"])
        self._run(["git", "commit", "-m", message])
        return self._run(["git", "rev-parse", "--short", "HEAD"]).strip()

    def push_current_branch(self) -> str:
        branch = self.status().branch
        if branch == "(detached)":
            raise GitOpsError("Cannot push from detached HEAD.")
        self._run(["git", "push", "-u", self.remote, branch])
        return branch

    def diff_for_review(self, *, max_chars: int = 30000) -> str:
        status = self._run(["git", "status", "--short"]).strip()
        stat = self._run(["git", "diff", "--stat"]).strip()
        diff = self._run(["git", "diff", "--"]).strip()
        combined = "\n".join(
            [
                "Git status:",
                status or "clean",
                "",
                "Diff stat:",
                stat or "no diff",
                "",
                "Diff:",
                diff or "no diff",
            ]
        )
        if len(combined) > max_chars:
            return f"{combined[: max_chars - 1]}..."
        return combined

    def create_pull_request(self, *, title: str, body: str, base_branch: str) -> str:
        branch = self.status().branch
        if branch == "(detached)":
            raise GitOpsError("Cannot create PR from detached HEAD.")
        output = self._run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--base",
                base_branch,
                "--head",
                branch,
            ]
        )
        return output.strip()

    def _run(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                args,
                cwd=self.project_root,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise GitOpsError(f"Command unavailable: {args[0]}") from exc
        except subprocess.CalledProcessError as exc:
            output = (exc.stderr or exc.stdout or "").strip()
            raise GitOpsError(output or f"Git command failed: {' '.join(args)}") from exc
        return result.stdout

    @staticmethod
    def _slugify(value: str) -> str:
        value = value.lower()
        value = re.sub(r"[^a-z0-9]+", "-", value, flags=re.IGNORECASE)
        value = value.strip("-")
        return value[:44] or "task"
