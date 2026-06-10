"""Ollama server performance settings — local env vars or Windows host instructions.

OLLAMA_FLASH_ATTENTION and OLLAMA_KV_CACHE_TYPE are read by the Ollama *server*
process at startup. When Ollama runs on Windows (accessed from WSL via OLLAMA_HOST),
setting these in WSL's ~/.bashrc has no effect — they must be set as Windows
user environment variables so the Windows Ollama process sees them.
"""

from __future__ import annotations

import os
from typing import Callable

from nimbus_tiers.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
    append_rc_export,
    default_rc_path,
    read_bashrc_value,
)


OLLAMA_HOST_VAR = "OLLAMA_HOST"

OLLAMA_SETTINGS: dict[str, str] = {
    "OLLAMA_FLASH_ATTENTION": "1",
    "OLLAMA_KV_CACHE_TYPE": "q8_0",
}

_WINDOWS_INSTRUCTIONS = """\
Ollama is running on Windows, so these settings must be applied there.
Setting them in WSL has no effect on the Windows Ollama process.

  Option 1 — PowerShell (recommended, run on Windows):
    setx OLLAMA_FLASH_ATTENTION 1
    setx OLLAMA_KV_CACHE_TYPE q8_0

  Option 2 — Windows Settings GUI:
    Settings → System → About → Advanced System Settings
    → Environment Variables → New (User variables)
      Name: OLLAMA_FLASH_ATTENTION   Value: 1
      Name: OLLAMA_KV_CACHE_TYPE     Value: q8_0

  After setting either way:
    Right-click the Ollama icon in the system tray → Quit, then relaunch it.\
"""


class OllamaServerConfigStep(SetupStep):
    name = "ollama-server-config"
    description = "Ollama server performance settings (flash attention, KV cache type)"

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

    def _is_remote(self) -> bool:
        return bool(self._env_lookup(OLLAMA_HOST_VAR))

    def check(self) -> CheckResult:
        if self._is_remote():
            return CheckResult(
                CheckStatus.PARTIAL,
                "remote Ollama — server settings must be configured on the Windows host",
            )
        missing = [k for k, v in OLLAMA_SETTINGS.items() if self._env_lookup(k) != v]
        if not missing:
            return CheckResult(
                CheckStatus.PRESENT,
                "OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0",
            )
        return CheckResult(CheckStatus.MISSING, f"not set: {', '.join(missing)}")

    def install(self, assume_yes: bool = False) -> InstallResult:
        if self._is_remote():
            self._log(_WINDOWS_INSTRUCTIONS)
            return InstallResult(
                InstallStatus.MANUAL,
                "set OLLAMA_FLASH_ATTENTION=1 and OLLAMA_KV_CACHE_TYPE=q8_0 in Windows "
                "Environment Variables, then restart Ollama from the system tray",
            )
        return self._set_local(assume_yes)

    def _set_local(self, assume_yes: bool) -> InstallResult:
        missing = {k: v for k, v in OLLAMA_SETTINGS.items() if self._env_lookup(k) != v}
        if not missing:
            return InstallResult(InstallStatus.SKIPPED, "all settings already present")
        already_in_rc = {k: v for k, v in missing.items() if self._rc_reader(k) == v}
        to_write = {k: v for k, v in missing.items() if k not in already_in_rc}
        if not to_write:
            return InstallResult(
                InstallStatus.INSTALLED,
                f"settings already in {self._rc_path}; run `source {self._rc_path}` to apply",
            )
        lines = "\n".join(f"    export {k}={v}" for k, v in to_write.items())
        prompt = f"Append these Ollama performance settings to {self._rc_path}?\n{lines}"
        if not self._ask(prompt, assume_yes):
            return InstallResult(InstallStatus.SKIPPED, "user declined")
        try:
            for k, v in to_write.items():
                self._rc_writer(k, v)
        except OSError as exc:
            return InstallResult(InstallStatus.FAILED, str(exc))
        return InstallResult(
            InstallStatus.INSTALLED,
            f"settings appended to {self._rc_path}; "
            f"restart your shell or `source {self._rc_path}` to apply",
        )


__all__ = ["OllamaServerConfigStep", "OLLAMA_SETTINGS", "OLLAMA_HOST_VAR"]
