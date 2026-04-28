"""Orchestrator that runs an ordered list of SetupSteps against the host.

Iterates each step's `check()`, prints status, and (if the step reports MISSING
or PARTIAL) asks the user whether to invoke `install()`. Honors `--check-only`
(skip all installs) and `--yes` (accept all installs without prompting).

Step ordering matters — Python comes before pip-installed tools, NVIDIA driver
before Ollama/TabbyAPI. Subclass step lists for other paths can reuse this
orchestrator unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    InstallResult,
    InstallStatus,
    SetupStep,
)


@dataclass
class StepReport:
    name: str
    description: str
    check: CheckResult
    install: InstallResult | None = None


@dataclass
class EnvironmentReport:
    steps: list[StepReport] = field(default_factory=list)

    @property
    def all_present(self) -> bool:
        for step in self.steps:
            if step.check.status is CheckStatus.PRESENT:
                continue
            if step.install is not None and step.install.status is InstallStatus.INSTALLED:
                continue
            return False
        return True

    def render(self) -> str:
        lines = []
        for s in self.steps:
            icon = _status_icon(s.check.status)
            lines.append(f"  {icon} {s.name:<16s} {s.check.status.value:<8s} {s.check.detail}")
            if s.install is not None:
                install_icon = _install_icon(s.install.status)
                lines.append(f"      {install_icon} install: {s.install.status.value} — {s.install.detail}")
        return "\n".join(lines)


def _status_icon(status: CheckStatus) -> str:
    return {
        CheckStatus.PRESENT: "[OK]",
        CheckStatus.PARTIAL: "[~~]",
        CheckStatus.MISSING: "[--]",
        CheckStatus.UNKNOWN: "[??]",
    }[status]


def _install_icon(status: InstallStatus) -> str:
    return {
        InstallStatus.INSTALLED: "[OK]",
        InstallStatus.SKIPPED: "[--]",
        InstallStatus.FAILED: "[!!]",
        InstallStatus.MANUAL: "[->]",
    }[status]


class EnvironmentSetup:
    """Composes a sequence of SetupStep instances into a single check/install run."""

    def __init__(self, steps: Sequence[SetupStep]) -> None:
        self.steps: list[SetupStep] = list(steps)

    def run(
        self,
        check_only: bool = False,
        assume_yes: bool = False,
    ) -> EnvironmentReport:
        report = EnvironmentReport()
        for step in self.steps:
            check = step.check()
            install: InstallResult | None = None
            if check.status is not CheckStatus.PRESENT and not check_only:
                install = step.install(assume_yes=assume_yes)
            report.steps.append(
                StepReport(
                    name=step.name,
                    description=step.description,
                    check=check,
                    install=install,
                )
            )
        return report


__all__ = [
    "EnvironmentSetup",
    "EnvironmentReport",
    "StepReport",
]
