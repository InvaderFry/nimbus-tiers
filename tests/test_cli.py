"""Tests for the generator CLI, focusing on --stack / TEST_CMD substitution."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nimbus_tiers.generator.cli import (
    STACK_TEST_COMMANDS,
    derive_class_name,
    derive_package_name,
    main,
)
from nimbus_tiers.generator.git_initializer import GitInitializer
from nimbus_tiers.resources import templates_root


REPO_TEMPLATES_ROOT = templates_root()


def _make_runner() -> MagicMock:
    return MagicMock(return_value=subprocess.CompletedProcess([], 0))


def _patched_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(
        "nimbus_tiers.generator.cli.GitInitializer",
        lambda: GitInitializer(runner=_make_runner()),
    )
    return main(argv)


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
    rc = _patched_main(monkeypatch, ["my-proj", "--path", str(project_dir), "--stack", stack])
    assert rc == 0
    aider_conf = (project_dir / ".aider.conf.yml").read_text()
    assert f"test-cmd: {expected_cmd}" in aider_conf


def test_cli_default_stack_is_java_maven(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "proj"
    rc = _patched_main(monkeypatch, ["my-proj", "--path", str(project_dir)])
    assert rc == 0
    aider_conf = (project_dir / ".aider.conf.yml").read_text()
    assert "test-cmd: ./mvnw test" in aider_conf


# ---------------------------------------------------------------------------
# Regression: the `.aider*` .gitignore glob must not exclude committed config
# ---------------------------------------------------------------------------


def test_generated_project_commits_aider_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The template .gitignore uses a broad ``.aider*`` glob to stop Aider
    rewriting .gitignore on startup. That glob also matches ``.aider.conf.yml``
    and ``.aiderignore`` — the two config files the generator writes — so without
    re-include negations, ``git add .`` silently drops them and the scaffold ships
    with no tracked Aider config (a regression the rest of the suite misses because
    it mocks git and only asserts on-disk presence). Drive the real generator and
    real git, then assert both files land in the index while transient ``.aider*``
    working files stay ignored.
    """
    if shutil.which("git") is None:
        pytest.skip("git not available")
    # Hermetic git: ignore host global/system config (e.g. enforced commit
    # signing) and supply identity via env so the initial commit succeeds
    # deterministically regardless of the runner's environment.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")

    project_dir = tmp_path / "proj"
    # Note: NOT _patched_main — we want the real GitInitializer so that the actual
    # ``git add .`` runs against the generated .gitignore. That integration is the
    # whole point of this guard.
    rc = main(["my-proj", "--path", str(project_dir), "--stack", "python"])
    assert rc == 0

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert ".aider.conf.yml" in tracked, (
        ".aider.conf.yml must be committed, not swallowed by the `.aider*` glob"
    )
    assert ".aiderignore" in tracked, (
        ".aiderignore must be committed, not swallowed by the `.aider*` glob"
    )

    # Transient Aider working files must still be ignored (they also match `.aider*`).
    (project_dir / ".aider.chat.history.md").write_text("transient\n")
    check = subprocess.run(
        ["git", "check-ignore", ".aider.chat.history.md"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, "transient `.aider*` working files must remain gitignored"


# ---------------------------------------------------------------------------
# Name derivation helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("my-app", "myapp"),
    ("my_app", "myapp"),
    ("myapp", "myapp"),
    ("WeatherService", "weatherservice"),
    ("123app", "app123app"),
])
def test_derive_package_name(name: str, expected: str) -> None:
    assert derive_package_name(name) == expected


@pytest.mark.parametrize("name,expected", [
    ("my-app", "MyApp"),
    ("my_app", "MyApp"),
    ("myapp", "Myapp"),
    ("weather-service", "WeatherService"),
    ("123proj", "App123proj"),
])
def test_derive_class_name(name: str, expected: str) -> None:
    assert derive_class_name(name) == expected


# ---------------------------------------------------------------------------
# Hello world source files land in the generated project
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stack,expected_files", [
    ("java-maven", ["pom.xml", "mvnw",
                    "src/main/java/com/example/myproj/MyProjApplication.java",
                    "src/test/java/com/example/myproj/MyProjApplicationTest.java",
                    "src/main/resources/application.properties"]),
    ("java-gradle", ["build.gradle", "settings.gradle", "gradlew",
                     "src/main/java/com/example/myproj/MyProjApplication.java"]),
    ("python", ["main.py", "requirements.txt", "tests/test_main.py"]),
    ("node", ["package.json", "index.js", "index.test.js"]),
])
def test_cli_generates_hello_world_files(
    tmp_path: Path,
    stack: str,
    expected_files: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "proj"
    rc = _patched_main(monkeypatch, ["my-proj", "--path", str(project_dir), "--stack", stack])
    assert rc == 0
    for rel in expected_files:
        assert (project_dir / rel).is_file(), f"missing: {rel}"


def test_cli_substitutes_package_and_class_in_java_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "proj"
    _patched_main(monkeypatch, ["my-proj", "--path", str(project_dir), "--stack", "java-maven"])
    src = (project_dir / "src/main/java/com/example/myproj/MyProjApplication.java").read_text()
    assert "package com.example.myproj;" in src
    assert "class MyProjApplication" in src
