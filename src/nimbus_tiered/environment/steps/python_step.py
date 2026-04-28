"""Python version check. Manual install."""

from __future__ import annotations

import sys

from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)


MIN_PYTHON = (3, 11)


class PythonStep(SetupStep):
    name = "python"
    description = f"Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}"

    def __init__(self, version_info: tuple[int, ...] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._version = version_info if version_info is not None else sys.version_info[:2]

    def check(self) -> CheckResult:
        if tuple(self._version) >= MIN_PYTHON:
            return CheckResult(
                CheckStatus.PRESENT,
                f"Python {self._version[0]}.{self._version[1]}",
            )
        return CheckResult(
            CheckStatus.MISSING,
            f"Python {self._version[0]}.{self._version[1]} found; "
            f"need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
        )

    def install(self, assume_yes: bool = False) -> InstallResult:
        return InstallResult(
            InstallStatus.MANUAL,
            "Install Python 3.11+ from https://www.python.org or your distro's package manager.",
        )


__all__ = ["PythonStep"]
