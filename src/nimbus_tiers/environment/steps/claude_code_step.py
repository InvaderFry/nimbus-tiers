"""Claude Code presence check. Manual install (npm-based)."""

from __future__ import annotations

from nimbus_tiers.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)


CLAUDE_INSTALL_HINT = (
    "Install Claude Code following the instructions at https://docs.claude.com/claude-code "
    "(typically `npm install -g @anthropic-ai/claude-code`)."
)


class ClaudeCodeStep(SetupStep):
    name = "claude-code"
    description = "Claude Code CLI (frontier planner / reviewer)"

    def check(self) -> CheckResult:
        if self._which("claude") is None:
            return CheckResult(CheckStatus.MISSING, "claude not on PATH")
        rc, stdout, stderr = self._capture("claude", "--version")
        if rc != 0:
            return CheckResult(
                CheckStatus.PARTIAL,
                f"claude present but `--version` failed: {stderr.strip() or stdout.strip()}",
            )
        return CheckResult(CheckStatus.PRESENT, stdout.strip() or "claude present")

    def install(self, assume_yes: bool = False) -> InstallResult:
        return InstallResult(InstallStatus.MANUAL, CLAUDE_INSTALL_HINT)


__all__ = ["ClaudeCodeStep", "CLAUDE_INSTALL_HINT"]
