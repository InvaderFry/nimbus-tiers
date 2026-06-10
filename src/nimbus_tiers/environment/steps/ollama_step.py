"""Ollama presence check + optional install or remote-endpoint configuration."""

from __future__ import annotations

import os
from typing import Callable

from nimbus_tiers.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    Prompter,
    SetupStep,
    append_rc_export,
    default_rc_path,
    read_bashrc_value,
)


OLLAMA_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"
OLLAMA_HOST_VAR = "OLLAMA_HOST"
# The installer downloads a multi-GB runtime; be generous, but never hang forever.
OLLAMA_INSTALL_TIMEOUT_S = 600


class OllamaStep(SetupStep):
    name = "ollama"
    description = "Ollama LLM runtime (port 11434)"

    def __init__(
        self,
        env_lookup: Callable[[str], str | None] | None = None,
        rc_writer: Callable[[str, str], None] | None = None,
        rc_reader: Callable[[str], str | None] | None = None,
        rc_path: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._rc_path = rc_path or default_rc_path()
        self._env_lookup = env_lookup if env_lookup is not None else os.environ.get
        self._rc_writer = rc_writer if rc_writer is not None else (
            lambda var, value: append_rc_export(var, value, self._rc_path)
        )
        self._rc_reader = rc_reader if rc_reader is not None else (
            lambda var: read_bashrc_value(var, self._rc_path)
        )

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
        existing = self._rc_reader(OLLAMA_HOST_VAR)
        if existing:
            self._log(f"Found {OLLAMA_HOST_VAR}={existing!r} in {self._rc_path}.")
            if self._confirm(f"Is {existing!r} the correct Ollama endpoint?"):
                return InstallResult(
                    InstallStatus.INSTALLED,
                    f"{OLLAMA_HOST_VAR} already in {self._rc_path}; "
                    f"run `source {self._rc_path}` to apply",
                )
        url = self._prompt("Ollama endpoint URL (e.g. http://192.168.1.100:11434)")
        if not url:
            return InstallResult(InstallStatus.SKIPPED, "no URL entered")
        if self._confirm(f"Append export {OLLAMA_HOST_VAR}={url!r} to {self._rc_path}?"):
            try:
                self._rc_writer(OLLAMA_HOST_VAR, url)
            except OSError as exc:
                return InstallResult(InstallStatus.FAILED, str(exc))
            return InstallResult(
                InstallStatus.INSTALLED,
                f"{OLLAMA_HOST_VAR}={url} written to {self._rc_path}; restart your shell to apply",
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
        rc, stdout, stderr = self._capture(
            "sh", "-c", OLLAMA_INSTALL_CMD, timeout=OLLAMA_INSTALL_TIMEOUT_S
        )
        if rc != 0:
            return InstallResult(
                InstallStatus.FAILED,
                f"installer exited {rc}: {stderr.strip() or stdout.strip()}",
            )
        return InstallResult(InstallStatus.INSTALLED, "Ollama installed locally")


__all__ = [
    "OllamaStep",
    "OLLAMA_INSTALL_CMD",
    "OLLAMA_HOST_VAR",
    "OLLAMA_INSTALL_TIMEOUT_S",
]
