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


def test_stack_test_commands_includes_go() -> None:
    assert "go" in STACK_TEST_COMMANDS
    assert STACK_TEST_COMMANDS["go"] == "go test ./..."


def test_stack_test_commands_includes_rust() -> None:
    assert "rust" in STACK_TEST_COMMANDS
    assert STACK_TEST_COMMANDS["rust"] == "cargo test --quiet"


# ---------------------------------------------------------------------------
# Template uses placeholder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path_type", ["full-hybrid", "light-local", "cloud-only"])
def test_aider_conf_template_contains_test_cmd_placeholder(path_type: str) -> None:
    content = (REPO_TEMPLATES_ROOT / "paths" / path_type / ".aider.conf.yml").read_text()
    assert "{{TEST_CMD}}" in content
    assert "test-cmd: pytest" not in content


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
        ("go", "go test ./..."),
        ("rust", "cargo test --quiet"),
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
# CLI integration: --path-type selects the matching Aider config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path_type, conf_marker, tabby_doc_expected",
    [
        ("full-hybrid", "Path C (Full Hybrid)", True),
        ("light-local", "Path B (Light Local)", False),
        ("cloud-only", "Path A (Cloud-Only)", False),
    ],
)
def test_cli_writes_path_specific_aider_conf(
    tmp_path: Path,
    path_type: str,
    conf_marker: str,
    tabby_doc_expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "proj"
    rc = _patched_main(
        monkeypatch,
        ["my-proj", "--path", str(project_dir), "--path-type", path_type, "--stack", "python"],
    )
    assert rc == 0
    aider_conf = (project_dir / ".aider.conf.yml").read_text()
    assert conf_marker in aider_conf
    assert "test-cmd: pytest -x --no-header" in aider_conf
    assert (project_dir / "docs" / "tabbyapi-nimbus-example.yml").is_file() is tabby_doc_expected
    # The shared skeleton lands regardless of path.
    for rel in ("phase2.sh", "PHASE1_SPEC.md", "CONTEXT.md", "main.py"):
        assert (project_dir / rel).is_file(), f"missing: {rel}"


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
    ("go", ["go.mod", "main.go", "main_test.go"]),
    ("rust", ["Cargo.toml", "src/main.rs"]),
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


# ---------------------------------------------------------------------------
# Wizard mode (interactive flow when project_name is omitted)
# ---------------------------------------------------------------------------


def _feed_input(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    answer_iter = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answer_iter))


def test_wizard_prompts_for_path_and_stack_by_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Prompt order: name, setup path, stack.
    # sorted paths: 1=cloud-only 2=full-hybrid 3=light-local
    # sorted stacks: 1=go 2=java-gradle 3=java-maven 4=node 5=python 6=rust
    project_dir = tmp_path / "proj"
    _feed_input(monkeypatch, ["wiz-proj", "3", "5"])
    rc = _patched_main(monkeypatch, ["--path", str(project_dir)])
    assert rc == 0
    conf = (project_dir / ".aider.conf.yml").read_text()
    assert "Path B (Light Local)" in conf
    assert "test-cmd: pytest -x --no-header" in conf


def test_wizard_enter_selects_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "proj"
    _feed_input(monkeypatch, ["wiz-proj", "", ""])
    rc = _patched_main(monkeypatch, ["--path", str(project_dir)])
    assert rc == 0
    conf = (project_dir / ".aider.conf.yml").read_text()
    assert "Path C (Full Hybrid)" in conf
    assert "test-cmd: ./mvnw test" in conf


def test_wizard_accepts_choice_names_and_flag_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --stack pinned by flag: the wizard must only prompt for name and path.
    project_dir = tmp_path / "proj"
    _feed_input(monkeypatch, ["wiz-proj", "cloud-only"])
    rc = _patched_main(monkeypatch, ["--path", str(project_dir), "--stack", "go"])
    assert rc == 0
    conf = (project_dir / ".aider.conf.yml").read_text()
    assert "Path A (Cloud-Only)" in conf
    assert "test-cmd: go test ./..." in conf


def test_wizard_rejects_invalid_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _feed_input(monkeypatch, ["wiz-proj", "99"])
    with pytest.raises(SystemExit, match="Invalid choice"):
        _patched_main(monkeypatch, ["--path", str(tmp_path / "proj")])


def test_explicit_project_name_never_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scripted invocations must stay 100% non-interactive."""
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt="": pytest.fail("input() must not be called with explicit args"),
    )
    project_dir = tmp_path / "proj"
    rc = _patched_main(monkeypatch, ["my-proj", "--path", str(project_dir)])
    assert rc == 0
    assert "test-cmd: ./mvnw test" in (project_dir / ".aider.conf.yml").read_text()


def test_cli_substitutes_package_name_in_go_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "proj"
    _patched_main(monkeypatch, ["my-proj", "--path", str(project_dir), "--stack", "go"])
    gomod = (project_dir / "go.mod").read_text()
    assert "module example.com/myproj" in gomod
    assert "{{PACKAGE_NAME}}" not in gomod


def test_cli_substitutes_package_name_in_cargo_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "proj"
    _patched_main(monkeypatch, ["my-proj", "--path", str(project_dir), "--stack", "rust"])
    cargo = (project_dir / "Cargo.toml").read_text()
    assert 'name = "myproj"' in cargo
    assert "{{PACKAGE_NAME}}" not in cargo
