"""Aider presence check + install via pipx.

pipx is preferred over plain pip because:
- Aider is a CLI tool, not a library — pipx is designed for exactly this.
- pipx creates and manages the venv internally; no activation needed.
- pipx avoids PEP 668 "externally-managed-environment" errors on macOS
  Homebrew Python and Ubuntu 23.04+/WSL.
"""

from __future__ import annotations

import sys

from nimbus_tiers.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)

_PIPX_INSTALL_INSTRUCTIONS = """\
pipx is not installed. Install it first, then run this setup again:

  macOS (Homebrew):
    brew install pipx
    pipx ensurepath

  Ubuntu / WSL (apt):
    sudo apt install pipx
    pipx ensurepath

  Any platform (pip --user, no system packages modified):
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath

  Then restart your shell and re-run setupEnvironment.py.\
"""


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
        if self._which("pipx") is None:
            self._log(_PIPX_INSTALL_INSTRUCTIONS)
            return InstallResult(
                InstallStatus.MANUAL,
                "install pipx (see instructions above), then re-run setupEnvironment.py",
            )
        return self._pipx_install(assume_yes)

    def _pipx_install(self, assume_yes: bool) -> InstallResult:
        prompt = (
            "Install Aider via pipx (isolated venv, global `aider` command, no system Python conflicts):\n"
            "    pipx install aider-chat\n"
            "Proceed?"
        )
        if not self._ask(prompt, assume_yes):
            return InstallResult(InstallStatus.SKIPPED, "user declined")
        rc, stdout, stderr = self._capture("pipx", "install", "aider-chat")
        if rc != 0:
            return InstallResult(
                InstallStatus.FAILED,
                f"pipx install exited {rc}: {stderr.strip() or stdout.strip()}",
            )
        return InstallResult(InstallStatus.INSTALLED, "Aider installed via pipx")


__all__ = ["AiderStep"]
