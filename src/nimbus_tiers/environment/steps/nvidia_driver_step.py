"""NVIDIA driver check. Manual install (requires sudo + reboot).

Platform-aware: on macOS there is no NVIDIA driver to check — Apple Silicon
has no CUDA, and Ollama uses the Metal backend instead. The light-local path
must be able to reach "Environment ready" on a Mac, so the check reports
PRESENT (not applicable) there; the full-hybrid path still fails correctly on
macOS at the TabbyAPI step, which genuinely requires CUDA on Linux/WSL.
"""

from __future__ import annotations

import re
import sys

from nimbus_tiers.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)


# Architecture doc baseline. Drivers older than this lack CUDA 12.8 support
# required by ExLlamaV3 on Blackwell.
MIN_DRIVER_MAJOR = 572
MIN_DRIVER_MINOR = 16

DRIVER_VERSION_RE = re.compile(r"Driver Version:\s*(\d+)\.(\d+)")

_DARWIN_DETAIL = (
    "not applicable on macOS — Ollama uses Apple Metal; the full-hybrid path "
    "(TabbyAPI/ExLlamaV3 + CUDA) requires Linux or WSL"
)


class NvidiaDriverStep(SetupStep):
    name = "nvidia-driver"
    description = f"NVIDIA driver >= {MIN_DRIVER_MAJOR}.{MIN_DRIVER_MINOR} (CUDA 12.8 capable)"

    def __init__(self, platform: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._platform = platform if platform is not None else sys.platform

    def check(self) -> CheckResult:
        if self._platform == "darwin":
            return CheckResult(CheckStatus.PRESENT, _DARWIN_DETAIL)
        if self._which("nvidia-smi") is None:
            return CheckResult(CheckStatus.MISSING, "nvidia-smi not on PATH")
        rc, stdout, stderr = self._capture("nvidia-smi")
        if rc != 0:
            return CheckResult(
                CheckStatus.UNKNOWN,
                f"nvidia-smi exited {rc}: {stderr.strip() or stdout.strip()}",
            )
        match = DRIVER_VERSION_RE.search(stdout)
        if not match:
            return CheckResult(CheckStatus.UNKNOWN, "could not parse driver version from nvidia-smi")
        major, minor = int(match.group(1)), int(match.group(2))
        if (major, minor) < (MIN_DRIVER_MAJOR, MIN_DRIVER_MINOR):
            return CheckResult(
                CheckStatus.PARTIAL,
                f"driver {major}.{minor} present but older than required "
                f"{MIN_DRIVER_MAJOR}.{MIN_DRIVER_MINOR}",
            )
        return CheckResult(CheckStatus.PRESENT, f"driver {major}.{minor}")

    def install(self, assume_yes: bool = False) -> InstallResult:
        if self._platform == "darwin":
            return InstallResult(InstallStatus.MANUAL, _DARWIN_DETAIL)
        return InstallResult(
            InstallStatus.MANUAL,
            "Install/upgrade the NVIDIA driver from https://www.nvidia.com/Download/index.aspx "
            "(requires sudo + reboot). On WSL, install on the Windows host, not inside WSL.",
        )


__all__ = ["NvidiaDriverStep"]
