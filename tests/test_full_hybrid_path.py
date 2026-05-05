"""Tests for FullHybridPath and the SetupPath ABC contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from nimbus_tiers.generator.full_hybrid_path import FullHybridPath
from nimbus_tiers.generator.setup_path import SetupPath, TemplateSpec


REPO_TEMPLATES_ROOT = Path(__file__).resolve().parents[1] / "templates"


def test_full_hybrid_name() -> None:
    assert FullHybridPath.name == "full-hybrid"


def test_full_hybrid_template_files_includes_core_artifacts() -> None:
    specs = FullHybridPath().template_files()
    dests = {spec.dest_relative for spec in specs}

    expected = {
        Path("CONTEXT.md"),
        Path("VERIFY.md"),
        Path("CLAUDE.md"),
        Path("NIMBUS_GUIDE.md"),
        Path(".aider.conf.yml"),
        Path(".aiderignore"),
        Path(".gitignore"),
        Path("plans/README.md"),
        Path("logs/ai-routing.csv"),
        Path("docs/architecture.md"),
    }
    assert expected.issubset(dests)


@pytest.mark.parametrize("stack,expected_dest", [
    ("java-maven", "pom.xml"),
    ("java-maven", "mvnw"),
    ("java-maven", "src/main/resources/application.properties"),
    ("java-gradle", "build.gradle"),
    ("java-gradle", "settings.gradle"),
    ("java-gradle", "gradlew"),
    ("python", "main.py"),
    ("python", "requirements.txt"),
    ("python", "tests/test_main.py"),
    ("node", "package.json"),
    ("node", "index.js"),
    ("node", "index.test.js"),
])
def test_full_hybrid_includes_stack_file(stack: str, expected_dest: str) -> None:
    dests = {str(s.dest_relative) for s in FullHybridPath(stack=stack).template_files()}
    assert expected_dest in dests


def test_full_hybrid_java_maven_application_dest_uses_package_name() -> None:
    specs = FullHybridPath(stack="java-maven", package_name="myapp").template_files()
    dests = {str(s.dest_relative) for s in specs}
    assert "src/main/java/com/example/myapp/Application.java" in dests
    assert "src/test/java/com/example/myapp/ApplicationTest.java" in dests


def test_full_hybrid_no_duplicate_destinations() -> None:
    for stack in ("java-maven", "java-gradle", "python", "node"):
        FullHybridPath(stack=stack).validate()


def test_full_hybrid_every_src_exists_in_templates_root() -> None:
    for stack in ("java-maven", "java-gradle", "python", "node"):
        for spec in FullHybridPath(stack=stack).template_files():
            full = REPO_TEMPLATES_ROOT / spec.src_relative
            assert full.is_file(), f"missing template: {full}"


def test_full_hybrid_no_absolute_paths() -> None:
    for spec in FullHybridPath().template_files():
        assert not spec.src_relative.is_absolute()
        assert not spec.dest_relative.is_absolute()


def test_template_spec_rejects_absolute_src() -> None:
    with pytest.raises(ValueError):
        TemplateSpec(Path("/abs/path"), Path("rel"))


def test_template_spec_rejects_absolute_dest() -> None:
    with pytest.raises(ValueError):
        TemplateSpec(Path("rel"), Path("/abs/path"))


def test_setup_path_validate_detects_duplicate_dests() -> None:
    class BadPath(SetupPath):
        name = "bad"

        def template_files(self) -> list[TemplateSpec]:
            return [
                TemplateSpec(Path("a.md"), Path("dest.md")),
                TemplateSpec(Path("b.md"), Path("dest.md")),
            ]

    with pytest.raises(ValueError, match="Duplicate destination"):
        BadPath().validate()


def test_setup_path_post_copy_hooks_default_noop(tmp_path: Path) -> None:
    class MinimalPath(SetupPath):
        name = "min"

        def template_files(self) -> list[TemplateSpec]:
            return []

    MinimalPath().post_copy_hooks(tmp_path)  # should not raise


def test_full_hybrid_unknown_stack_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported stack"):
        FullHybridPath(stack="ruby")._stack_template_files()


@pytest.mark.parametrize("filename", ["Application.java", "ApplicationTest.java", "application.properties"])
def test_java_maven_and_gradle_share_identical_source_templates(filename: str) -> None:
    maven = (REPO_TEMPLATES_ROOT / "stacks" / "java-maven" / filename).read_bytes()
    gradle = (REPO_TEMPLATES_ROOT / "stacks" / "java-gradle" / filename).read_bytes()
    assert maven == gradle, (
        f"stacks/java-maven/{filename} and stacks/java-gradle/{filename} have diverged. "
        "Update both files to keep them in sync."
    )


@pytest.mark.parametrize("stack,script", [
    ("java-maven", "mvnw"),
    ("java-gradle", "gradlew"),
])
def test_post_copy_hooks_makes_wrapper_executable(
    tmp_path: Path, stack: str, script: str
) -> None:
    (tmp_path / script).write_text("#!/bin/sh\n")
    FullHybridPath(stack=stack).post_copy_hooks(tmp_path)
    assert (tmp_path / script).stat().st_mode & 0o111, f"{script} should be executable"


def test_post_copy_hooks_tolerates_missing_wrapper(tmp_path: Path) -> None:
    FullHybridPath(stack="java-maven").post_copy_hooks(tmp_path)  # mvnw absent — should not raise
