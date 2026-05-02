"""Git initialization for newly-generated projects.

Runs `git init`, stages everything, and creates a single initial commit. Idempotent:
if `.git/` already exists, it skips with a warning. Never configures a remote and
never pushes.
"""

from __future__ import annotations

import enum
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


DEFAULT_COMMIT_MESSAGE = "Initial scaffold from nimbus-tiers architecture template"


class GitInitAction(enum.Enum):
    INITIALIZED = "initialized"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class GitInitResult:
    action: GitInitAction
    detail: str = ""


class GitInitializer:
    """Initialize git in a project directory and make an initial commit."""

    def __init__(
        self,
        commit_message: str = DEFAULT_COMMIT_MESSAGE,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
    ) -> None:
        self.commit_message = commit_message
        self._run = runner if runner is not None else subprocess.run

    def initialize(self, project_path: Path) -> GitInitResult:
        if not project_path.is_dir():
            return GitInitResult(GitInitAction.FAILED, f"not a directory: {project_path}")

        if (project_path / ".git").exists():
            return GitInitResult(GitInitAction.SKIPPED, ".git already present")

        if shutil.which("git") is None:
            return GitInitResult(GitInitAction.SKIPPED, "git not found on PATH")

        try:
            self._git(project_path, "init")
            self._git(project_path, "add", ".")
            self._git(project_path, "commit", "-m", self.commit_message)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            return GitInitResult(
                GitInitAction.FAILED,
                f"git command failed (rc={exc.returncode}): {stderr}",
            )

        return GitInitResult(GitInitAction.INITIALIZED, self.commit_message)

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess:
        return self._run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
        )


__all__ = ["GitInitializer", "GitInitResult", "GitInitAction", "DEFAULT_COMMIT_MESSAGE"]
