"""Tests for ProjectGenerator and GitInitializer."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nimbus_tiered.generator.file_writer import (
    FileWriter,
    WriteAction,
    WriteMode,
    WriteResult,
)
from nimbus_tiered.generator.git_initializer import (
    DEFAULT_COMMIT_MESSAGE,
    GitInitAction,
    GitInitializer,
)
from nimbus_tiered.generator.project_generator import (
    GenerationReport,
    ProjectGenerator,
)
from nimbus_tiered.generator.setup_path import SetupPath, TemplateSpec


class _FakePath(SetupPath):
    name = "fake"

    def __init__(self, specs: list[TemplateSpec]) -> None:
        self._specs = specs

    def template_files(self) -> list[TemplateSpec]:
        return list(self._specs)


@pytest.fixture
def templates_root(tmp_path: Path) -> Path:
    root = tmp_path / "templates"
    (root / "nested").mkdir(parents=True)
    (root / "a.md").write_text("hello {{PROJECT_NAME}}\n")
    (root / "nested" / "b.md").write_text("nested\n")
    return root


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    return tmp_path / "project"


def test_generate_writes_each_template_and_substitutes(
    templates_root: Path, project_path: Path
) -> None:
    setup = _FakePath(
        [
            TemplateSpec(Path("a.md"), Path("a.md")),
            TemplateSpec(Path("nested/b.md"), Path("deep/b.md")),
        ]
    )
    git = MagicMock(spec=GitInitializer)
    git.initialize.return_value = GitInitializer().initialize.__annotations__.get(
        "return", None
    )
    git.initialize.return_value = GitInitializer()._git.__annotations__.get(
        "return", None
    )
    # Build a real GitInitResult using subprocess mock
    real_runner = MagicMock(return_value=subprocess.CompletedProcess([], 0))
    git_real = GitInitializer(runner=real_runner)
    generator = ProjectGenerator(
        setup_path=setup,
        file_writer=FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None),
        git_initializer=git_real,
        templates_root=templates_root,
    )

    report = generator.generate("demo", project_path)

    assert (project_path / "a.md").read_text() == "hello demo\n"
    assert (project_path / "deep" / "b.md").read_text() == "nested\n"
    assert report.project_name == "demo"
    assert report.setup_path_name == "fake"
    assert report.summary().get("written") == 2


def test_generate_creates_destination_directory(
    templates_root: Path, project_path: Path
) -> None:
    setup = _FakePath([TemplateSpec(Path("a.md"), Path("a.md"))])
    git = GitInitializer(runner=MagicMock(return_value=subprocess.CompletedProcess([], 0)))
    generator = ProjectGenerator(
        setup_path=setup,
        file_writer=FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None),
        git_initializer=git,
        templates_root=templates_root,
    )

    assert not project_path.exists()
    generator.generate("demo", project_path)
    assert project_path.is_dir()


def test_generate_refuses_when_dest_is_a_file(
    templates_root: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "exists.txt"
    dest.write_text("not a dir")
    setup = _FakePath([TemplateSpec(Path("a.md"), Path("a.md"))])
    git = GitInitializer()
    generator = ProjectGenerator(
        setup_path=setup,
        file_writer=FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None),
        git_initializer=git,
        templates_root=templates_root,
    )

    with pytest.raises(NotADirectoryError):
        generator.generate("demo", dest)


def test_generate_skips_existing_files_on_rerun(
    templates_root: Path, project_path: Path
) -> None:
    setup = _FakePath([TemplateSpec(Path("a.md"), Path("a.md"))])
    git = GitInitializer(runner=MagicMock(return_value=subprocess.CompletedProcess([], 0)))
    generator = ProjectGenerator(
        setup_path=setup,
        file_writer=FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None),
        git_initializer=git,
        templates_root=templates_root,
    )

    generator.generate("demo", project_path)
    # Modify the file so it's not "unchanged"
    (project_path / "a.md").write_text("user edits\n")
    second = generator.generate("demo", project_path)

    assert second.summary().get("skipped") == 1
    assert (project_path / "a.md").read_text() == "user edits\n"


def test_generate_propagates_substitutions(
    templates_root: Path, project_path: Path
) -> None:
    (templates_root / "extra.md").write_text("k={{EXTRA_KEY}}\n")
    setup = _FakePath(
        [
            TemplateSpec(Path("a.md"), Path("a.md")),
            TemplateSpec(Path("extra.md"), Path("extra.md")),
        ]
    )
    git = GitInitializer(runner=MagicMock(return_value=subprocess.CompletedProcess([], 0)))
    generator = ProjectGenerator(
        setup_path=setup,
        file_writer=FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None),
        git_initializer=git,
        templates_root=templates_root,
    )

    generator.generate("demo", project_path, substitutions={"EXTRA_KEY": "value"})

    assert (project_path / "extra.md").read_text() == "k=value\n"


def test_generate_invokes_post_copy_hooks(
    templates_root: Path, project_path: Path
) -> None:
    captured: list[Path] = []

    class HookedPath(SetupPath):
        name = "hooked"

        def template_files(self) -> list[TemplateSpec]:
            return [TemplateSpec(Path("a.md"), Path("a.md"))]

        def post_copy_hooks(self, project_root: Path) -> None:
            captured.append(project_root)

    git = GitInitializer(runner=MagicMock(return_value=subprocess.CompletedProcess([], 0)))
    generator = ProjectGenerator(
        setup_path=HookedPath(),
        file_writer=FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None),
        git_initializer=git,
        templates_root=templates_root,
    )

    generator.generate("demo", project_path)
    assert captured == [project_path]


def test_git_initializer_skips_when_already_initialized(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / ".git").mkdir(parents=True)
    git = GitInitializer(runner=MagicMock(side_effect=AssertionError("must not run")))

    result = git.initialize(project)

    assert result.action is GitInitAction.SKIPPED


def test_git_initializer_runs_init_add_commit(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    runner = MagicMock(return_value=subprocess.CompletedProcess([], 0))
    git = GitInitializer(runner=runner)

    result = git.initialize(project)

    assert result.action is GitInitAction.INITIALIZED
    invoked = [tuple(call.args[0]) for call in runner.call_args_list]
    assert invoked == [
        ("git", "init"),
        ("git", "add", "."),
        ("git", "commit", "-m", DEFAULT_COMMIT_MESSAGE),
    ]


def test_git_initializer_reports_failure_on_called_process_error(
    tmp_path: Path,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    runner = MagicMock(
        side_effect=subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "commit"],
            stderr=b"please tell me who you are",
        )
    )
    git = GitInitializer(runner=runner)

    result = git.initialize(project)

    assert result.action is GitInitAction.FAILED
    assert "please tell me who you are" in result.detail


def test_generation_report_render_includes_counts(tmp_path: Path) -> None:
    report = GenerationReport(
        project_name="demo",
        project_path=tmp_path,
        setup_path_name="fake",
        file_results=[
            WriteResult(WriteAction.WRITTEN, tmp_path / "a"),
            WriteResult(WriteAction.WRITTEN, tmp_path / "b"),
            WriteResult(WriteAction.SKIPPED, tmp_path / "c"),
        ],
    )
    output = report.render()
    assert "written: 2" in output
    assert "skipped: 1" in output
    assert "demo" in output
