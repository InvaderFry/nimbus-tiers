"""Groq API key check + optional persist to ~/.bashrc."""

from __future__ import annotations

import os
from typing import Callable

from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)


GROQ_API_KEY_VAR = "GROQ_API_KEY"
GROQ_CONSOLE_URL = "https://console.groq.com/keys"


def _append_bashrc_export(var: str, value: str) -> None:
    path = os.path.expanduser("~/.bashrc")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f'export {var}="{value}"\n')


class GroqApiKeyStep(SetupStep):
    name = "groq-api-key"
    description = f"Groq API key ({GROQ_API_KEY_VAR}) for free-tier cloud fallback"

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
        key = self._env_lookup(GROQ_API_KEY_VAR)
        if not key:
            return CheckResult(
                CheckStatus.MISSING,
                f"{GROQ_API_KEY_VAR} not set — needed for Groq free-tier fallback (Tiers 0 and 2)",
            )
        # Show only a short prefix so the value is recognisable but not exposed in logs.
        preview = key[:8] + "..." if len(key) > 8 else "***"
        return CheckResult(CheckStatus.PRESENT, f"{GROQ_API_KEY_VAR}={preview}")

    def install(self, assume_yes: bool = False) -> InstallResult:
        self._log(
            f"\nGroq is used as the free-tier cloud fallback (Tiers 0 and 2) in Aider sessions.\n"
            f"Get a free API key at: {GROQ_CONSOLE_URL}\n"
        )

        if assume_yes:
            return InstallResult(
                InstallStatus.MANUAL,
                f"set {GROQ_API_KEY_VAR} in your shell or ~/.bashrc and re-run to verify",
            )

        key = self._prompt(f"Paste your Groq API key (or press Enter to skip)")
        if not key:
            return InstallResult(InstallStatus.SKIPPED, "no key entered")

        if self._confirm(f"Append export {GROQ_API_KEY_VAR}=... to ~/.bashrc?"):
            try:
                self._rc_writer(GROQ_API_KEY_VAR, key)
            except OSError as exc:
                return InstallResult(InstallStatus.FAILED, str(exc))
            return InstallResult(
                InstallStatus.INSTALLED,
                f"{GROQ_API_KEY_VAR} written to ~/.bashrc; restart your shell or `source ~/.bashrc` to apply",
            )

        return InstallResult(
            InstallStatus.SKIPPED,
            f"key not persisted; set {GROQ_API_KEY_VAR} manually to keep it",
        )


__all__ = ["GroqApiKeyStep", "GROQ_API_KEY_VAR", "GROQ_CONSOLE_URL"]
