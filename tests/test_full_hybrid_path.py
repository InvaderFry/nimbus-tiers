"""Tests for FullHybridPath and the SetupPath ABC contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from nimbus_tiered.generator.full_hybrid_path import FullHybridPath
from nimbus_tiered.generator.setup_path import SetupPath, TemplateSpec


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


def test_full_hybrid_no_duplicate_destinations() -> None:
    FullHybridPath().validate()  # raises on duplicate


def test_full_hybrid_every_src_exists_in_templates_root() -> None:
    for spec in FullHybridPath().template_files():
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
