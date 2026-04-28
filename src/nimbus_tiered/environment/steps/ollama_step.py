"""Ollama presence check + optional install via the official one-liner."""

from __future__ import annotations

from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)


OLLAMA_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"


class OllamaStep(SetupStep):
    name = "ollama"
    description = "Ollama LLM runtime (port 11434)"

    def check(self) -> CheckResult:
        if self._which("ollama") is None:
            return CheckResult(CheckStatus.MISSING, "ollama not on PATH")
        rc, stdout, stderr = self._capture("ollama", "--version")
        if rc != 0:
            return CheckResult(
                CheckStatus.PARTIAL,
                f"ollama present but `--version` failed: {stderr.strip() or stdout.strip()}",
            )
        return CheckResult(CheckStatus.PRESENT, stdout.strip() or "ollama present")

    def install(self, assume_yes: bool = False) -> InstallResult:
        prompt = (
            "Install Ollama by running:\n"
            f"    {OLLAMA_INSTALL_CMD}\n"
            "Proceed?"
        )
        if not self._ask(prompt, assume_yes):
            return InstallResult(InstallStatus.SKIPPED, "user declined")
        rc, stdout, stderr = self._capture("sh", "-c", OLLAMA_INSTALL_CMD)
        if rc != 0:
            return InstallResult(
                InstallStatus.FAILED,
                f"installer exited {rc}: {stderr.strip() or stdout.strip()}",
            )
        return InstallResult(InstallStatus.INSTALLED, "Ollama installed")


__all__ = ["OllamaStep", "OLLAMA_INSTALL_CMD"]
