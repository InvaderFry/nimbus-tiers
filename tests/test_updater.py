"""Tests for nimbus-update (template-drift upgrader) and the generation manifest."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nimbus_tiers.generator.cli import main as generate_main
from nimbus_tiers.generator.full_hybrid_path import FullHybridPath
from nimbus_tiers.generator.git_initializer import GitInitializer
from nimbus_tiers.generator.project_generator import MANIFEST_NAME
from nimbus_tiers.updater.cli import main as update_main


def _generate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs) -> Path:
    """Scaffold a python-stack project with git mocked out; return its path."""
    project = tmp_path / "proj"
    monkeypatch.setattr(
        "nimbus_tiers.generator.cli.GitInitializer",
        lambda: GitInitializer(
            runner=MagicMock(return_value=subprocess.CompletedProcess([], 0))
        ),
    )
    argv = ["my-proj", "--path", str(project), "--stack", "python"]
    for key, value in kwargs.items():
        argv += [f"--{key.replace('_', '-')}", value]
    assert generate_main(argv) == 0
    return project


# ---------------------------------------------------------------------------
# Generation manifest
# ---------------------------------------------------------------------------


def test_generator_writes_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _generate(tmp_path, monkeypatch, path_type="light-local")
    manifest = json.loads((project / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest == {
        "format": 1,
        "path_type": "light-local",
        "stack": "python",
        "project_name": "my-proj",
        "package_name": "myproj",
        "class_name": "MyProj",
    }


def test_manifest_is_deterministic_across_reruns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    first = (project / MANIFEST_NAME).read_bytes()
    # Re-run over the existing project (skip mode): manifest must byte-match
    # so it reports `unchanged`, not `skipped`.
    assert generate_main(["my-proj", "--path", str(project), "--stack", "python"]) == 0
    assert (project / MANIFEST_NAME).read_bytes() == first


# ---------------------------------------------------------------------------
# Managed / user-owned classification
# ---------------------------------------------------------------------------


def test_managed_specs_cover_the_tool_owned_files() -> None:
    specs = {str(s.dest_relative): s.managed for s in FullHybridPath(stack="python").template_files()}
    for managed_file in (
        "phase2.sh",
        "phase2-lib.sh",
        "PHASE1_SPEC.md",
        "NIMBUS_GUIDE.md",
        "PHASE1_VERIFY_HELPER.md",
        ".aiderignore",
        "docs/architecture.md",
        "docs/tabbyapi-nimbus-example.yml",
    ):
        assert specs[managed_file], f"{managed_file} should be managed"
    for user_file in (
        "CONTEXT.md",
        "VERIFY.md",
        "CLAUDE.md",
        ".aider.conf.yml",
        ".gitignore",
        "logs/ai-routing.csv",
        "main.py",
        "tests/test_main.py",
    ):
        assert not specs[user_file], f"{user_file} must stay user-owned"


# ---------------------------------------------------------------------------
# nimbus-update behavior
# ---------------------------------------------------------------------------


def test_update_diff_mode_reports_but_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _generate(tmp_path, monkeypatch)
    drifted = project / "phase2.sh"
    drifted.write_text("#!/usr/bin/env bash\necho outdated copy\n", encoding="utf-8")

    assert update_main(["--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "Diff mode: nothing was written" in out
    assert drifted.read_text(encoding="utf-8") == "#!/usr/bin/env bash\necho outdated copy\n"


def test_update_apply_restores_managed_and_spares_user_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    (project / "phase2.sh").write_text("outdated\n", encoding="utf-8")
    (project / "CONTEXT.md").write_text("my precious invariants\n", encoding="utf-8")
    (project / "main.py").write_text("print('my real code')\n", encoding="utf-8")

    assert update_main(["--path", str(project), "--apply"]) == 0

    restored = (project / "phase2.sh").read_text(encoding="utf-8")
    assert "Phase 2 executor" in restored, "managed file must be restored from template"
    assert (project / "CONTEXT.md").read_text(encoding="utf-8") == "my precious invariants\n"
    assert (project / "main.py").read_text(encoding="utf-8") == "print('my real code')\n"


def test_update_force_all_extends_to_user_owned_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    (project / "CONTEXT.md").write_text("stale\n", encoding="utf-8")

    assert update_main(["--path", str(project), "--force-all"]) == 0
    assert (project / "CONTEXT.md").read_text(encoding="utf-8") != "stale\n"


def test_update_apply_preserves_substitutions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-synced managed files must re-apply the project's own substitutions."""
    project = _generate(tmp_path, monkeypatch)
    guide = project / "NIMBUS_GUIDE.md"
    guide.write_text("outdated\n", encoding="utf-8")

    assert update_main(["--path", str(project), "--apply"]) == 0
    content = guide.read_text(encoding="utf-8")
    assert "# my-proj" in content, "PROJECT_NAME substitution must be re-applied"
    assert "{{PROJECT_NAME}}" not in content


def test_update_refuses_without_manifest_or_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    (project / MANIFEST_NAME).unlink()
    with pytest.raises(SystemExit, match="--path-type"):
        update_main(["--path", str(project), "--apply"])


def test_update_premanifest_project_with_flags_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    (project / MANIFEST_NAME).unlink()
    (project / "phase2.sh").write_text("outdated\n", encoding="utf-8")

    rc = update_main(
        ["--path", str(project), "--apply", "--path-type", "full-hybrid", "--stack", "python"]
    )
    assert rc == 0
    assert "Phase 2 executor" in (project / "phase2.sh").read_text(encoding="utf-8")
    manifest = json.loads((project / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["path_type"] == "full-hybrid"
    assert manifest["stack"] == "python"


def test_update_apply_refuses_dirty_git_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _generate(tmp_path, monkeypatch)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "uncommitted.txt").write_text("wip\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="uncommitted"):
        update_main(["--path", str(project), "--apply"])
    # Diff mode is always allowed on a dirty tree.
    assert update_main(["--path", str(project)]) == 0


def test_update_missing_project_dir_fails(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="not found"):
        update_main(["--path", str(tmp_path / "nope")])
