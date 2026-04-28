"""Aider presence check + optional install via aider-install."""

from __future__ import annotations

import sys

from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)


class AiderStep(SetupStep):
    name = "aider"
    description = "Aider terminal coding agent"

    def check(self) -> CheckResult:
        if self._which("aider") is None:
            return CheckResult(CheckStatus.MISSING, "aider not on PATH")
        rc, stdout, stderr = self._capture("aider", "--version")
        if rc != 0:
            return CheckResult(
                CheckStatus.PARTIAL,
                f"aider present but `--version` failed: {stderr.strip() or stdout.strip()}",
            )
        return CheckResult(CheckStatus.PRESENT, stdout.strip() or "aider present")

    def install(self, assume_yes: bool = False) -> InstallResult:
        prompt = (
            "Install Aider with:\n"
            f"    {sys.executable} -m pip install aider-install\n"
            f"    {sys.executable} -m aider_install\n"
            "Proceed?"
        )
        if not self._ask(prompt, assume_yes):
            return InstallResult(InstallStatus.SKIPPED, "user declined")
        rc, stdout, stderr = self._capture(
            sys.executable, "-m", "pip", "install", "aider-install"
        )
        if rc != 0:
            return InstallResult(
                InstallStatus.FAILED,
                f"pip install exited {rc}: {stderr.strip() or stdout.strip()}",
            )
        rc, stdout, stderr = self._capture(sys.executable, "-m", "aider_install")
        if rc != 0:
            return InstallResult(
                InstallStatus.FAILED,
                f"aider_install exited {rc}: {stderr.strip() or stdout.strip()}",
            )
        return InstallResult(InstallStatus.INSTALLED, "Aider installed via aider-install")


__all__ = ["AiderStep"]
