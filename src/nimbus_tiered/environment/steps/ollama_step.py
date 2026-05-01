"""Ollama presence check + optional install or remote-endpoint configuration."""

from __future__ import annotations

import os
from typing import Callable

from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    Prompter,
    SetupStep,
)


OLLAMA_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"
OLLAMA_HOST_VAR = "OLLAMA_HOST"


def _append_bashrc_export(var: str, value: str) -> None:
    path = os.path.expanduser("~/.bashrc")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f'export {var}="{value}"\n')


class OllamaStep(SetupStep):
    name = "ollama"
    description = "Ollama LLM runtime (port 11434)"

    def __init__(
        self,
        env_lookup: Callable[[str], str | None] | None = None,
        rc_writer: Callable[[str, str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._env_lookup = env_lookup if env_lookup is not None else os.environ.get
        self._rc_writer = rc_writer if rc_writer is not None else _append_bashrc_export

    def check(self) -> CheckResult:
        host = self._env_lookup(OLLAMA_HOST_VAR)
        if host:
            return CheckResult(CheckStatus.PRESENT, f"remote endpoint configured: {host}")
        if self._which("ollama") is None:
            return CheckResult(
                CheckStatus.MISSING,
                f"ollama not on PATH and {OLLAMA_HOST_VAR} not set",
            )
        rc, stdout, stderr = self._capture("ollama", "--version")
        if rc != 0:
            return CheckResult(
                CheckStatus.PARTIAL,
                f"ollama present but `--version` failed: {stderr.strip() or stdout.strip()}",
            )
        return CheckResult(CheckStatus.PRESENT, stdout.strip() or "ollama present")

    def install(self, assume_yes: bool = False) -> InstallResult:
        if not assume_yes:
            self._log(
                "\nOllama is not available locally. How would you like to configure it?\n"
                "  [r] Use a remote endpoint (e.g. Ollama running on your Windows host)\n"
                "  [i] Install locally\n"
                "  [s] Skip"
            )
            choice = (self._prompt("Choice [r/i/s]") or "s").strip().lower()
            if choice == "r":
                return self._configure_remote()
            if choice == "s":
                return InstallResult(InstallStatus.SKIPPED, "user skipped")
        return self._install_local(assume_yes)

    def _configure_remote(self) -> InstallResult:
        url = self._prompt("Ollama endpoint URL (e.g. http://192.168.1.100:11434)")
        if not url:
            return InstallResult(InstallStatus.SKIPPED, "no URL entered")
        if self._confirm(f"Append export {OLLAMA_HOST_VAR}={url!r} to ~/.bashrc?"):
            try:
                self._rc_writer(OLLAMA_HOST_VAR, url)
            except OSError as exc:
                return InstallResult(InstallStatus.FAILED, str(exc))
            return InstallResult(
                InstallStatus.INSTALLED,
                f"{OLLAMA_HOST_VAR}={url} written to ~/.bashrc; restart your shell to apply",
            )
        return InstallResult(
            InstallStatus.SKIPPED,
            f"endpoint noted but not persisted ({url}); set {OLLAMA_HOST_VAR} manually to keep it",
        )

    def _install_local(self, assume_yes: bool) -> InstallResult:
        prompt = (
            "Install Ollama locally by running:\n"
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
        return InstallResult(InstallStatus.INSTALLED, "Ollama installed locally")


__all__ = ["OllamaStep", "OLLAMA_INSTALL_CMD", "OLLAMA_HOST_VAR"]
