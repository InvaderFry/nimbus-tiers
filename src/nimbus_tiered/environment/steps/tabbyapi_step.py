"""TabbyAPI checkout check + optional clone.

We don't auto-run start.py — it triggers a long Flash Attention build that the
user should kick off interactively. We only verify that the checkout exists.
"""

from __future__ import annotations

import os
from pathlib import Path

from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)


TABBY_REPO = "https://github.com/theroyallab/tabbyAPI"
DEFAULT_TABBY_PATH = "~/tabbyapi"


class TabbyApiStep(SetupStep):
    name = "tabbyapi"
    description = "TabbyAPI inference backend (ExLlamaV3, port 5000)"

    def __init__(self, tabby_path: str = DEFAULT_TABBY_PATH, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tabby_path = tabby_path

    def _resolved_path(self) -> Path:
        return Path(os.path.expanduser(self.tabby_path))

    def check(self) -> CheckResult:
        path = self._resolved_path()
        if not path.is_dir():
            return CheckResult(CheckStatus.MISSING, f"no checkout at {path}")
        if not (path / "start.py").is_file():
            return CheckResult(
                CheckStatus.PARTIAL,
                f"checkout at {path} but start.py is missing — wrong directory?",
            )
        return CheckResult(CheckStatus.PRESENT, f"checkout at {path}")

    def install(self, assume_yes: bool = False) -> InstallResult:
        path = self._resolved_path()
        if path.exists():
            return InstallResult(
                InstallStatus.SKIPPED,
                f"{path} already exists; remove or specify a different path",
            )
        if self._which("git") is None:
            return InstallResult(InstallStatus.FAILED, "git not on PATH")
        prompt = f"Clone TabbyAPI ({TABBY_REPO}) into {path}?"
        if not self._ask(prompt, assume_yes):
            return InstallResult(InstallStatus.SKIPPED, "user declined")
        rc, stdout, stderr = self._capture("git", "clone", TABBY_REPO, str(path))
        if rc != 0:
            return InstallResult(
                InstallStatus.FAILED,
                f"git clone exited {rc}: {stderr.strip() or stdout.strip()}",
            )
        return InstallResult(
            InstallStatus.INSTALLED,
            f"cloned to {path}; run `cd {path} && python start.py` to finish setup",
        )


__all__ = ["TabbyApiStep", "TABBY_REPO", "DEFAULT_TABBY_PATH"]
