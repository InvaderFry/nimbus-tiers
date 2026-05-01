"""Abstract base class for environment-setup steps.

A SetupStep is a single check-and-optionally-install operation against the host
machine. Concrete steps implement `check()` (always safe to run) and optionally
`install()` (only invoked after explicit user consent).

The orchestrator (EnvironmentSetup) calls `check()` first; if the result is
missing or partial, it asks the user before calling `install()`. Steps that
cannot be auto-installed (NVIDIA driver, Python, Claude Code) override `install`
to print manual instructions instead.
"""

from __future__ import annotations

import enum
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable


class CheckStatus(enum.Enum):
    PRESENT = "present"
    MISSING = "missing"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class InstallStatus(enum.Enum):
    INSTALLED = "installed"
    SKIPPED = "skipped"
    FAILED = "failed"
    MANUAL = "manual"  # user must do it themselves


@dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    detail: str = ""


@dataclass(frozen=True)
class InstallResult:
    status: InstallStatus
    detail: str = ""


# Caller-supplied callbacks. Defaults pull from real subprocess and stdin.
Runner = Callable[..., subprocess.CompletedProcess]
Confirm = Callable[[str], bool]
Logger = Callable[[str], None]
Prompter = Callable[[str], "str | None"]


def default_confirm(prompt: str) -> bool:
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def default_prompter(prompt: str) -> "str | None":
    try:
        value = input(f"{prompt}: ").strip()
    except EOFError:
        return None
    return value or None


def default_runner(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(*args, **kwargs)


def default_logger(message: str) -> None:
    print(message)


class SetupStep(ABC):
    """Subclass per dependency. Each step is independently testable."""

    name: str = "abstract"
    description: str = ""

    def __init__(
        self,
        runner: Runner | None = None,
        confirm: Confirm | None = None,
        logger: Logger | None = None,
        prompter: Prompter | None = None,
    ) -> None:
        self._run = runner if runner is not None else default_runner
        self._confirm = confirm if confirm is not None else default_confirm
        self._log = logger if logger is not None else default_logger
        self._prompter = prompter if prompter is not None else default_prompter

    @abstractmethod
    def check(self) -> CheckResult:
        raise NotImplementedError

    def install(self, assume_yes: bool = False) -> InstallResult:
        """Default behavior: not auto-installable. Override in subclasses that can."""
        return InstallResult(
            InstallStatus.MANUAL,
            f"{self.name} cannot be auto-installed; install it manually.",
        )

    # Convenience helpers for subclasses ----------------------------------

    def _which(self, command: str) -> str | None:
        return shutil.which(command)

    def _capture(self, *args: str) -> tuple[int, str, str]:
        """Run a command, capture output, never raise. Returns (rc, stdout, stderr)."""
        try:
            proc = self._run(
                list(args),
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            return 127, "", str(exc)
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _prompt(self, label: str) -> str | None:
        return self._prompter(label)

    def _ask(self, prompt: str, assume_yes: bool) -> bool:
        if assume_yes:
            self._log(f"[--yes] {prompt}")
            return True
        return self._confirm(prompt)


class EnvVarStep(SetupStep):
    """Generic env-var presence check + optional rc-file append."""

    def __init__(
        self,
        var_name: str,
        expected_value: str,
        rc_path: str = "~/.bashrc",
        env_lookup: Callable[[str], str | None] | None = None,
        rc_writer: Callable[[str, str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.var_name = var_name
        self.expected_value = expected_value
        self.rc_path = rc_path
        self.name = f"env:{var_name}"
        self.description = f"Environment variable {var_name}={expected_value}"
        self._env_lookup = env_lookup if env_lookup is not None else os.environ.get
        self._rc_writer = rc_writer if rc_writer is not None else self._default_rc_writer

    def check(self) -> CheckResult:
        actual = self._env_lookup(self.var_name)
        if actual is None:
            return CheckResult(CheckStatus.MISSING, f"{self.var_name} not set in environment")
        if actual != self.expected_value:
            return CheckResult(
                CheckStatus.PARTIAL,
                f"{self.var_name}={actual!r}, expected {self.expected_value!r}",
            )
        return CheckResult(CheckStatus.PRESENT, f"{self.var_name}={actual}")

    def install(self, assume_yes: bool = False) -> InstallResult:
        prompt = (
            f"Append `export {self.var_name}={self.expected_value}` to {self.rc_path}?"
        )
        if not self._ask(prompt, assume_yes):
            return InstallResult(InstallStatus.SKIPPED, "user declined")
        try:
            self._rc_writer(self.rc_path, f'export {self.var_name}="{self.expected_value}"\n')
        except OSError as exc:
            return InstallResult(InstallStatus.FAILED, str(exc))
        return InstallResult(
            InstallStatus.INSTALLED,
            f"appended to {self.rc_path}; restart your shell or `source {self.rc_path}` to apply",
        )

    @staticmethod
    def _default_rc_writer(rc_path: str, line: str) -> None:
        expanded = os.path.expanduser(rc_path)
        with open(expanded, "a", encoding="utf-8") as fh:
            fh.write(line)


__all__ = [
    "CheckStatus",
    "InstallStatus",
    "CheckResult",
    "InstallResult",
    "SetupStep",
    "EnvVarStep",
    "Prompter",
    "default_confirm",
    "default_prompter",
    "default_runner",
    "default_logger",
]
