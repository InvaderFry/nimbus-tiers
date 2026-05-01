"""Tests for environment SetupStep implementations and the EnvironmentSetup orchestrator.

All subprocess and prompt calls are mocked — these tests must run on any machine
regardless of whether the underlying tools are installed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nimbus_tiered.environment.environment_setup import (
    EnvironmentSetup,
    EnvironmentReport,
)
from nimbus_tiered.environment.setup_step import (
    CheckResult,
    CheckStatus,
    EnvVarStep,
    InstallResult,
    InstallStatus,
    SetupStep,
)
from nimbus_tiered.environment.steps import (
    AiderStep,
    ClaudeCodeStep,
    NvidiaDriverStep,
    OllamaStep,
    PythonStep,
    TabbyApiStep,
)


def _proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


# ----- PythonStep -----------------------------------------------------------


def test_python_step_present_for_modern_version() -> None:
    step = PythonStep(version_info=(3, 12))
    result = step.check()
    assert result.status is CheckStatus.PRESENT


def test_python_step_missing_for_old_version() -> None:
    step = PythonStep(version_info=(3, 9))
    result = step.check()
    assert result.status is CheckStatus.MISSING


def test_python_step_install_is_manual() -> None:
    step = PythonStep(version_info=(3, 9))
    result = step.install()
    assert result.status is InstallStatus.MANUAL


# ----- NvidiaDriverStep -----------------------------------------------------


def test_nvidia_driver_present_when_recent_version_parsed() -> None:
    runner = MagicMock(return_value=_proc(stdout="Driver Version: 575.20  CUDA Version: 12.8\n"))
    step = NvidiaDriverStep(runner=runner)
    # Patch _which to pretend nvidia-smi is on PATH
    step._which = lambda _cmd: "/usr/bin/nvidia-smi"  # type: ignore[method-assign]
    result = step.check()
    assert result.status is CheckStatus.PRESENT
    assert "575" in result.detail


def test_nvidia_driver_partial_when_old_version() -> None:
    runner = MagicMock(return_value=_proc(stdout="Driver Version: 535.10\n"))
    step = NvidiaDriverStep(runner=runner)
    step._which = lambda _cmd: "/usr/bin/nvidia-smi"  # type: ignore[method-assign]
    result = step.check()
    assert result.status is CheckStatus.PARTIAL


def test_nvidia_driver_missing_when_no_smi() -> None:
    step = NvidiaDriverStep()
    step._which = lambda _cmd: None  # type: ignore[method-assign]
    result = step.check()
    assert result.status is CheckStatus.MISSING


# ----- OllamaStep -----------------------------------------------------------


def test_ollama_check_missing_when_not_on_path() -> None:
    step = OllamaStep(env_lookup=lambda _k: None)
    step._which = lambda _cmd: None  # type: ignore[method-assign]
    assert step.check().status is CheckStatus.MISSING


def test_ollama_check_present_when_version_runs() -> None:
    runner = MagicMock(return_value=_proc(stdout="ollama version 0.1.39\n"))
    step = OllamaStep(runner=runner, env_lookup=lambda _k: None)
    step._which = lambda _cmd: "/usr/local/bin/ollama"  # type: ignore[method-assign]
    result = step.check()
    assert result.status is CheckStatus.PRESENT


def test_ollama_check_present_when_ollama_host_set() -> None:
    step = OllamaStep(env_lookup=lambda _k: "http://192.168.1.100:11434")
    result = step.check()
    assert result.status is CheckStatus.PRESENT
    assert "192.168.1.100" in result.detail


def test_ollama_install_skipped_when_user_chooses_skip() -> None:
    step = OllamaStep(prompter=lambda _p: "s", logger=lambda _m: None)
    result = step.install()
    assert result.status is InstallStatus.SKIPPED


def test_ollama_install_skipped_when_user_declines_local() -> None:
    # 'i' → local install → user says no
    step = OllamaStep(
        prompter=lambda _p: "i",
        confirm=lambda _p: False,
        logger=lambda _m: None,
    )
    result = step.install()
    assert result.status is InstallStatus.SKIPPED


def test_ollama_install_runs_official_oneliner_when_i_chosen() -> None:
    runner = MagicMock(return_value=_proc(stdout="ok"))
    step = OllamaStep(
        runner=runner,
        prompter=lambda _p: "i",
        confirm=lambda _p: True,
        logger=lambda _m: None,
    )
    result = step.install()
    assert result.status is InstallStatus.INSTALLED
    invoked = runner.call_args[0][0]
    assert invoked[0:2] == ["sh", "-c"]
    assert "ollama.com/install.sh" in invoked[2]


def test_ollama_install_assume_yes_runs_local_install() -> None:
    runner = MagicMock(return_value=_proc(stdout="ok"))
    step = OllamaStep(runner=runner, logger=lambda _m: None)
    result = step.install(assume_yes=True)
    assert result.status is InstallStatus.INSTALLED


def test_ollama_install_remote_persists_url() -> None:
    captured: list[tuple[str, str]] = []
    prompts = iter(["r", "http://192.168.1.100:11434"])
    step = OllamaStep(
        prompter=lambda _p: next(prompts),
        confirm=lambda _p: True,
        logger=lambda _m: None,
        rc_writer=lambda var, val: captured.append((var, val)),
    )
    result = step.install()
    assert result.status is InstallStatus.INSTALLED
    assert captured == [("OLLAMA_HOST", "http://192.168.1.100:11434")]


def test_ollama_install_remote_skipped_when_no_url_entered() -> None:
    prompts = iter(["r", ""])
    step = OllamaStep(
        prompter=lambda _p: next(prompts) or None,
        logger=lambda _m: None,
    )
    result = step.install()
    assert result.status is InstallStatus.SKIPPED


def test_ollama_install_remote_not_persisted_when_user_declines_bashrc() -> None:
    prompts = iter(["r", "http://192.168.1.100:11434"])
    step = OllamaStep(
        prompter=lambda _p: next(prompts),
        confirm=lambda _p: False,
        logger=lambda _m: None,
    )
    result = step.install()
    assert result.status is InstallStatus.SKIPPED
    assert "not persisted" in result.detail


# ----- TabbyApiStep ---------------------------------------------------------


def test_tabbyapi_missing_when_path_does_not_exist(tmp_path: Path) -> None:
    step = TabbyApiStep(tabby_path=str(tmp_path / "nope"), env_lookup=lambda _k: None)
    assert step.check().status is CheckStatus.MISSING


def test_tabbyapi_partial_when_dir_lacks_start_py(tmp_path: Path) -> None:
    (tmp_path / "tabbyapi").mkdir()
    step = TabbyApiStep(
        tabby_path=str(tmp_path / "tabbyapi"), env_lookup=lambda _k: None
    )
    assert step.check().status is CheckStatus.PARTIAL


def test_tabbyapi_present_when_start_py_exists(tmp_path: Path) -> None:
    target = tmp_path / "tabbyapi"
    target.mkdir()
    (target / "start.py").write_text("# stub\n")
    step = TabbyApiStep(tabby_path=str(target), env_lookup=lambda _k: None)
    assert step.check().status is CheckStatus.PRESENT


def test_tabbyapi_check_present_when_url_env_set(tmp_path: Path) -> None:
    step = TabbyApiStep(
        tabby_path=str(tmp_path / "nope"),
        env_lookup=lambda _k: "http://192.168.1.100:5000",
    )
    result = step.check()
    assert result.status is CheckStatus.PRESENT
    assert "192.168.1.100" in result.detail


def test_tabbyapi_install_skipped_when_user_chooses_skip() -> None:
    step = TabbyApiStep(prompter=lambda _p: "s", logger=lambda _m: None)
    result = step.install()
    assert result.status is InstallStatus.SKIPPED


def test_tabbyapi_install_remote_persists_url() -> None:
    captured: list[tuple[str, str]] = []
    prompts = iter(["r", "http://192.168.1.100:5000"])
    step = TabbyApiStep(
        prompter=lambda _p: next(prompts),
        confirm=lambda _p: True,
        logger=lambda _m: None,
        rc_writer=lambda var, val: captured.append((var, val)),
    )
    result = step.install()
    assert result.status is InstallStatus.INSTALLED
    assert captured == [("TABBYAPI_URL", "http://192.168.1.100:5000")]


def test_tabbyapi_install_remote_not_persisted_when_user_declines_bashrc() -> None:
    prompts = iter(["r", "http://192.168.1.100:5000"])
    step = TabbyApiStep(
        prompter=lambda _p: next(prompts),
        confirm=lambda _p: False,
        logger=lambda _m: None,
    )
    result = step.install()
    assert result.status is InstallStatus.SKIPPED
    assert "not persisted" in result.detail


def test_tabbyapi_install_assume_yes_clones_locally(tmp_path: Path) -> None:
    runner = MagicMock(return_value=_proc())
    step = TabbyApiStep(
        tabby_path=str(tmp_path / "tabbyapi"),
        runner=runner,
        logger=lambda _m: None,
    )
    step._which = lambda _cmd: "/usr/bin/git"  # type: ignore[method-assign]
    result = step.install(assume_yes=True)
    assert result.status is InstallStatus.INSTALLED


# ----- AiderStep ------------------------------------------------------------


def test_aider_check_missing_when_not_on_path() -> None:
    step = AiderStep()
    step._which = lambda _cmd: None  # type: ignore[method-assign]
    assert step.check().status is CheckStatus.MISSING


def test_aider_install_skipped_when_user_declines() -> None:
    step = AiderStep(confirm=lambda _p: False)
    assert step.install().status is InstallStatus.SKIPPED


# ----- ClaudeCodeStep -------------------------------------------------------


def test_claude_code_install_is_manual() -> None:
    step = ClaudeCodeStep()
    assert step.install().status is InstallStatus.MANUAL


# ----- EnvVarStep -----------------------------------------------------------


def test_env_var_step_present_when_value_matches() -> None:
    step = EnvVarStep(
        "FOO",
        "1",
        env_lookup=lambda _k: "1",
    )
    assert step.check().status is CheckStatus.PRESENT


def test_env_var_step_partial_when_value_differs() -> None:
    step = EnvVarStep(
        "FOO",
        "1",
        env_lookup=lambda _k: "0",
    )
    assert step.check().status is CheckStatus.PARTIAL


def test_env_var_step_missing_when_unset() -> None:
    step = EnvVarStep(
        "FOO",
        "1",
        env_lookup=lambda _k: None,
    )
    assert step.check().status is CheckStatus.MISSING


def test_env_var_step_install_appends_to_rc(tmp_path: Path) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text("# existing\n")
    captured: list[tuple[str, str]] = []

    def fake_writer(path: str, line: str) -> None:
        captured.append((path, line))

    step = EnvVarStep(
        "FOO",
        "1",
        rc_path=str(rc),
        env_lookup=lambda _k: None,
        rc_writer=fake_writer,
        confirm=lambda _p: True,
        logger=lambda _m: None,
    )
    result = step.install()
    assert result.status is InstallStatus.INSTALLED
    assert captured == [(str(rc), 'export FOO="1"\n')]


# ----- EnvironmentSetup orchestrator ----------------------------------------


class _FakeStep(SetupStep):
    def __init__(self, name: str, status: CheckStatus, install_status: InstallStatus) -> None:
        super().__init__()
        self.name = name
        self._status = status
        self._install_status = install_status

    def check(self) -> CheckResult:
        return CheckResult(self._status, "fake")

    def install(self, assume_yes: bool = False) -> InstallResult:
        return InstallResult(self._install_status, "fake-install")


def test_orchestrator_skips_install_in_check_only_mode() -> None:
    step = _FakeStep("a", CheckStatus.MISSING, InstallStatus.INSTALLED)
    setup = EnvironmentSetup([step])
    report = setup.run(check_only=True)
    assert report.steps[0].install is None


def test_orchestrator_runs_install_when_missing() -> None:
    step = _FakeStep("a", CheckStatus.MISSING, InstallStatus.INSTALLED)
    setup = EnvironmentSetup([step])
    report = setup.run(check_only=False, assume_yes=True)
    assert report.steps[0].install is not None
    assert report.steps[0].install.status is InstallStatus.INSTALLED


def test_orchestrator_all_present_true_when_every_step_present() -> None:
    a = _FakeStep("a", CheckStatus.PRESENT, InstallStatus.SKIPPED)
    b = _FakeStep("b", CheckStatus.PRESENT, InstallStatus.SKIPPED)
    setup = EnvironmentSetup([a, b])
    assert setup.run(check_only=True).all_present


def test_orchestrator_all_present_true_after_successful_install() -> None:
    step = _FakeStep("a", CheckStatus.MISSING, InstallStatus.INSTALLED)
    setup = EnvironmentSetup([step])
    assert setup.run(check_only=False, assume_yes=True).all_present


def test_orchestrator_all_present_false_when_install_failed() -> None:
    step = _FakeStep("a", CheckStatus.MISSING, InstallStatus.FAILED)
    setup = EnvironmentSetup([step])
    assert not setup.run(check_only=False, assume_yes=True).all_present


def test_environment_report_render_includes_all_step_names() -> None:
    a = _FakeStep("first", CheckStatus.PRESENT, InstallStatus.SKIPPED)
    b = _FakeStep("second", CheckStatus.MISSING, InstallStatus.MANUAL)
    setup = EnvironmentSetup([a, b])
    report = setup.run(check_only=True)
    rendered = report.render()
    assert "first" in rendered
    assert "second" in rendered
