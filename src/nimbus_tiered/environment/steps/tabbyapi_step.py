"""TabbyAPI presence check + optional remote-endpoint config or local clone."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    Prompter,
    SetupStep,
)


TABBY_REPO = "https://github.com/theroyallab/tabbyAPI"
DEFAULT_TABBY_PATH = "~/tabbyapi"
TABBYAPI_URL_VAR = "TABBYAPI_URL"


def _append_bashrc_export(var: str, value: str) -> None:
    path = os.path.expanduser("~/.bashrc")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f'export {var}="{value}"\n')


class TabbyApiStep(SetupStep):
    name = "tabbyapi"
    description = "TabbyAPI inference backend (ExLlamaV3, port 5000)"

    def __init__(
        self,
        tabby_path: str = DEFAULT_TABBY_PATH,
        env_lookup: Callable[[str], str | None] | None = None,
        rc_writer: Callable[[str, str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tabby_path = tabby_path
        self._env_lookup = env_lookup if env_lookup is not None else os.environ.get
        self._rc_writer = rc_writer if rc_writer is not None else _append_bashrc_export

    def _resolved_path(self) -> Path:
        return Path(os.path.expanduser(self.tabby_path))

    def check(self) -> CheckResult:
        url = self._env_lookup(TABBYAPI_URL_VAR)
        if url:
            return CheckResult(CheckStatus.PRESENT, f"remote endpoint configured: {url}")
        path = self._resolved_path()
        if not path.is_dir():
            return CheckResult(
                CheckStatus.MISSING,
                f"no checkout at {path} and {TABBYAPI_URL_VAR} not set",
            )
        if not (path / "start.py").is_file():
            return CheckResult(
                CheckStatus.PARTIAL,
                f"checkout at {path} but start.py is missing — wrong directory?",
            )
        return CheckResult(CheckStatus.PRESENT, f"checkout at {path}")

    def install(self, assume_yes: bool = False) -> InstallResult:
        if not assume_yes:
            self._log(
                "\nTabbyAPI is not available locally. How would you like to configure it?\n"
                "  [r] Use a remote endpoint (e.g. TabbyAPI running on your Windows host)\n"
                "  [i] Clone locally\n"
                "  [s] Skip"
            )
            choice = (self._prompt("Choice [r/i/s]") or "s").strip().lower()
            if choice == "r":
                return self._configure_remote()
            if choice == "s":
                return InstallResult(InstallStatus.SKIPPED, "user skipped")
        return self._clone_local(assume_yes)

    def _configure_remote(self) -> InstallResult:
        url = self._prompt("TabbyAPI endpoint URL (e.g. http://192.168.1.100:5000)")
        if not url:
            return InstallResult(InstallStatus.SKIPPED, "no URL entered")
        self._log(
            "\nNote: if your TabbyAPI instance has authentication enabled, you will also\n"
            "need to set TABBYAPI_API_KEY in your shell. Find the key in config.yml on\n"
            "your Windows host (api_key field), then add it to ~/.bashrc:\n"
            "    export TABBYAPI_API_KEY=\"your-key-here\"\n"
        )
        if self._confirm(f"Append export {TABBYAPI_URL_VAR}={url!r} to ~/.bashrc?"):
            try:
                self._rc_writer(TABBYAPI_URL_VAR, url)
            except OSError as exc:
                return InstallResult(InstallStatus.FAILED, str(exc))
            return InstallResult(
                InstallStatus.INSTALLED,
                f"{TABBYAPI_URL_VAR}={url} written to ~/.bashrc; restart your shell to apply",
            )
        return InstallResult(
            InstallStatus.SKIPPED,
            f"endpoint noted but not persisted ({url}); set {TABBYAPI_URL_VAR} manually to keep it",
        )

    def _clone_local(self, assume_yes: bool) -> InstallResult:
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


__all__ = ["TabbyApiStep", "TABBY_REPO", "DEFAULT_TABBY_PATH", "TABBYAPI_URL_VAR"]
