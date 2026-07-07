"""Tests for the three setup paths sharing the StackScaffoldPath scaffold."""

from __future__ import annotations

from pathlib import Path

import pytest

from nimbus_tiers.generator.cloud_only_path import CloudOnlyPath
from nimbus_tiers.generator.full_hybrid_path import FullHybridPath
from nimbus_tiers.generator.light_local_path import LightLocalPath
from nimbus_tiers.generator.stack_scaffold_path import StackScaffoldPath
from nimbus_tiers.resources import templates_root


ALL_PATHS = [CloudOnlyPath, LightLocalPath, FullHybridPath]
ALL_STACKS = ["java-maven", "java-gradle", "python", "node", "go", "rust"]

TABBY_DOC_DEST = Path("docs/tabbyapi-nimbus-example.yml")


@pytest.mark.parametrize("path_cls,expected_name", [
    (CloudOnlyPath, "cloud-only"),
    (LightLocalPath, "light-local"),
    (FullHybridPath, "full-hybrid"),
])
def test_path_names(path_cls: type[StackScaffoldPath], expected_name: str) -> None:
    assert path_cls.name == expected_name


@pytest.mark.parametrize("path_cls", ALL_PATHS)
def test_aider_conf_is_path_specific(path_cls: type[StackScaffoldPath]) -> None:
    """Each path must copy its own paths/<name>/.aider.conf.yml to the project root."""
    specs = {s.dest_relative: s.src_relative for s in path_cls().template_files()}
    assert specs[Path(".aider.conf.yml")] == Path(
        f"paths/{path_cls.name}/.aider.conf.yml"
    )


@pytest.mark.parametrize("path_cls", ALL_PATHS)
@pytest.mark.parametrize("stack", ALL_STACKS)
def test_every_src_exists_in_templates_root(
    path_cls: type[StackScaffoldPath], stack: str
) -> None:
    for spec in path_cls(stack=stack).template_files():
        full = templates_root() / spec.src_relative
        assert full.is_file(), f"missing template: {full}"


@pytest.mark.parametrize("path_cls", ALL_PATHS)
@pytest.mark.parametrize("stack", ALL_STACKS)
def test_no_duplicate_destinations(
    path_cls: type[StackScaffoldPath], stack: str
) -> None:
    path_cls(stack=stack).validate()


def test_tabbyapi_example_only_ships_with_full_hybrid() -> None:
    """The TabbyAPI server example is meaningless without TabbyAPI — only Path C copies it."""
    full_hybrid_dests = {s.dest_relative for s in FullHybridPath().template_files()}
    assert TABBY_DOC_DEST in full_hybrid_dests
    for path_cls in (CloudOnlyPath, LightLocalPath):
        dests = {s.dest_relative for s in path_cls().template_files()}
        assert TABBY_DOC_DEST not in dests, f"{path_cls.name} must not copy the TabbyAPI doc"


@pytest.mark.parametrize("path_cls", ALL_PATHS)
def test_paths_share_the_common_skeleton(path_cls: type[StackScaffoldPath]) -> None:
    dests = {s.dest_relative for s in path_cls().template_files()}
    expected = {
        Path("CONTEXT.md"),
        Path("VERIFY.md"),
        Path("CLAUDE.md"),
        Path("NIMBUS_GUIDE.md"),
        Path("PHASE1_SPEC.md"),
        Path("phase2.sh"),
        Path("phase2-lib.sh"),
        Path(".aider.conf.yml"),
        Path(".aiderignore"),
        Path(".gitignore"),
        Path("plans/README.md"),
        Path("logs/ai-routing.csv"),
        Path("docs/architecture.md"),
        Path("PHASE1_VERIFY_HELPER.md"),
    }
    assert expected.issubset(dests)


@pytest.mark.parametrize("path_cls", ALL_PATHS)
def test_unknown_stack_raises(path_cls: type[StackScaffoldPath]) -> None:
    with pytest.raises(ValueError, match="Unsupported stack"):
        path_cls(stack="ruby").template_files()


# ---------------------------------------------------------------------------
# Per-path Aider config content contracts
# ---------------------------------------------------------------------------


def _conf_text(path_name: str) -> str:
    return (templates_root() / "paths" / path_name / ".aider.conf.yml").read_text()


def test_light_local_conf_targets_ollama() -> None:
    conf = _conf_text("light-local")
    assert "openai-api-base: http://localhost:11434/v1" in conf


def test_cloud_only_conf_targets_groq_with_no_local_endpoint() -> None:
    conf = _conf_text("cloud-only")
    assert "model: groq/" in conf
    assert "openai-api-base" not in conf


def test_full_hybrid_conf_targets_tabbyapi() -> None:
    conf = _conf_text("full-hybrid")
    assert "openai-api-base: http://localhost:5000/v1" in conf


@pytest.mark.parametrize("path_name", ["cloud-only", "light-local", "full-hybrid"])
def test_all_confs_keep_phase2_contract(path_name: str) -> None:
    """phase2.sh owns commits/tests and injects the TEST_CMD substitution."""
    conf = _conf_text(path_name)
    assert "test-cmd: {{TEST_CMD}}" in conf
    assert "auto-commits: false" in conf
    assert "auto-test: false" in conf
