"""Tests for the generator CLI, focusing on --stack / TEST_CMD substitution."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nimbus_tiers.generator.cli import STACK_TEST_COMMANDS, main
from nimbus_tiers.generator.git_initializer import GitInitializer


REPO_TEMPLATES_ROOT = Path(__file__).resolve().parents[1] / "templates"


def _make_runner() -> MagicMock:
    return MagicMock(return_value=subprocess.CompletedProcess([], 0))


# ---------------------------------------------------------------------------
# STACK_TEST_COMMANDS contract
# ---------------------------------------------------------------------------


def test_stack_test_commands_includes_python() -> None:
    assert "python" in STACK_TEST_COMMANDS
    assert STACK_TEST_COMMANDS["python"] == "pytest -x --no-header"


def test_stack_test_commands_includes_java_maven() -> None:
    assert "java-maven" in STACK_TEST_COMMANDS
    assert STACK_TEST_COMMANDS["java-maven"] == "./mvnw test"


def test_stack_test_commands_includes_java_gradle() -> None:
    assert "java-gradle" in STACK_TEST_COMMANDS
    assert STACK_TEST_COMMANDS["java-gradle"] == "./gradlew test"


def test_stack_test_commands_includes_node() -> None:
    assert "node" in STACK_TEST_COMMANDS
    assert STACK_TEST_COMMANDS["node"] == "npm test"


# ---------------------------------------------------------------------------
# Template uses placeholder
# ---------------------------------------------------------------------------


def test_aider_conf_template_contains_test_cmd_placeholder() -> None:
    content = (REPO_TEMPLATES_ROOT / ".aider.conf.yml").read_text()
    assert "{{TEST_CMD}}" in content
    assert "pytest" not in content


# ---------------------------------------------------------------------------
# CLI integration: substitution lands in generated .aider.conf.yml
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stack, expected_cmd",
    [
        ("python", "pytest -x --no-header"),
        ("java-maven", "./mvnw test"),
        ("java-gradle", "./gradlew test"),
        ("node", "npm test"),
    ],
)
def test_cli_writes_correct_test_cmd_for_stack(
    tmp_path: Path, stack: str, expected_cmd: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "proj"
    monkeypatch.setattr(
        "nimbus_tiers.generator.git_initializer.GitInitializer._git",
        lambda self, *args, **kwargs: subprocess.CompletedProcess([], 0),
        raising=False,
    )
    # Patch GitInitializer runner to avoid real git calls
    monkeypatch.setattr(
        "nimbus_tiers.generator.cli.GitInitializer",
        lambda: GitInitializer(runner=_make_runner()),
    )

    rc = main(["my-proj", "--path", str(project_dir), "--stack", stack])

    assert rc == 0
    aider_conf = (project_dir / ".aider.conf.yml").read_text()
    assert f"test-cmd: {expected_cmd}" in aider_conf


def test_cli_default_stack_is_java_maven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "proj"
    monkeypatch.setattr(
        "nimbus_tiers.generator.cli.GitInitializer",
        lambda: GitInitializer(runner=_make_runner()),
    )

    rc = main(["my-proj", "--path", str(project_dir)])

    assert rc == 0
    aider_conf = (project_dir / ".aider.conf.yml").read_text()
    assert "test-cmd: ./mvnw test" in aider_conf
