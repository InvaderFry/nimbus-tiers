"""Tests for nimbus_tiers.generator.file_writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from nimbus_tiers.generator.file_writer import (
    FileWriter,
    WriteAction,
    WriteMode,
)


@pytest.fixture
def src_file(tmp_path: Path) -> Path:
    src = tmp_path / "src" / "template.md"
    src.parent.mkdir(parents=True)
    src.write_text("hello {{PROJECT_NAME}}\n")
    return src


def _captured_log() -> tuple[list[str], "callable"]:
    captured: list[str] = []
    return captured, captured.append


def test_skip_writes_when_dest_missing(tmp_path: Path, src_file: Path) -> None:
    dest = tmp_path / "out" / "template.md"
    writer = FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None)

    result = writer.write(src_file, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.WRITTEN
    assert dest.read_text() == "hello demo\n"


def test_skip_skips_when_dest_exists(tmp_path: Path, src_file: Path) -> None:
    dest = tmp_path / "out" / "template.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("user content\n")
    log, append = _captured_log()
    writer = FileWriter(mode=WriteMode.SKIP, log=append)

    result = writer.write(src_file, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.SKIPPED
    assert dest.read_text() == "user content\n"
    assert any("[skip]" in line for line in log)


def test_skip_reports_unchanged_when_identical(tmp_path: Path, src_file: Path) -> None:
    dest = tmp_path / "out" / "template.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("hello demo\n")
    writer = FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None)

    result = writer.write(src_file, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.UNCHANGED


def test_force_overwrites_existing_dest(tmp_path: Path, src_file: Path) -> None:
    dest = tmp_path / "out" / "template.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("user content\n")
    writer = FileWriter(mode=WriteMode.FORCE, log=lambda _msg: None)

    result = writer.write(src_file, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.WRITTEN
    assert dest.read_text() == "hello demo\n"


def test_diff_prints_unified_diff_without_writing(
    tmp_path: Path, src_file: Path
) -> None:
    dest = tmp_path / "out" / "template.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("user content\n")
    log, append = _captured_log()
    writer = FileWriter(mode=WriteMode.DIFF, log=append)

    result = writer.write(src_file, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.DIFFED
    assert dest.read_text() == "user content\n"  # NOT modified
    log_text = "\n".join(log)
    assert "user content" in log_text
    assert "hello demo" in log_text


def test_diff_reports_no_changes(tmp_path: Path, src_file: Path) -> None:
    dest = tmp_path / "out" / "template.md"
    dest.parent.mkdir(parents=True)
    dest.write_text("hello demo\n")
    log, append = _captured_log()
    writer = FileWriter(mode=WriteMode.DIFF, log=append)

    result = writer.write(src_file, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.DIFFED
    assert any("no changes" in line for line in log)


def test_diff_reports_new_file(tmp_path: Path, src_file: Path) -> None:
    dest = tmp_path / "out" / "missing.md"
    log, append = _captured_log()
    writer = FileWriter(mode=WriteMode.DIFF, log=append)

    result = writer.write(src_file, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.DIFFED
    assert not dest.exists()
    assert any("would create" in line for line in log)


def test_creates_nested_parent_directories(tmp_path: Path, src_file: Path) -> None:
    dest = tmp_path / "deep" / "nested" / "path" / "out.md"
    writer = FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None)

    result = writer.write(src_file, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.WRITTEN
    assert dest.exists()


def test_binary_file_copied_verbatim(tmp_path: Path) -> None:
    src = tmp_path / "src" / "icon.bin"
    src.parent.mkdir(parents=True)
    payload = bytes(range(256))
    src.write_bytes(payload)
    dest = tmp_path / "out" / "icon.bin"
    writer = FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None)

    result = writer.write(src, dest, {"PROJECT_NAME": "demo"})

    assert result.action is WriteAction.WRITTEN
    assert dest.read_bytes() == payload


def test_dir_at_dest_raises(tmp_path: Path, src_file: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    writer = FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None)

    with pytest.raises(IsADirectoryError):
        writer.write(src_file, dest)


def test_missing_src_raises(tmp_path: Path) -> None:
    src = tmp_path / "missing.md"
    dest = tmp_path / "out.md"
    writer = FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None)

    with pytest.raises(FileNotFoundError):
        writer.write(src, dest)


def test_copy_tree_processes_every_file(tmp_path: Path) -> None:
    src_root = tmp_path / "templates"
    (src_root / "a").mkdir(parents=True)
    (src_root / "a" / "x.md").write_text("x for {{PROJECT_NAME}}\n")
    (src_root / "y.md").write_text("y\n")
    (src_root / ".hidden").write_text("hidden\n")

    dest_root = tmp_path / "project"
    writer = FileWriter(mode=WriteMode.SKIP, log=lambda _msg: None)

    results = writer.copy_tree(src_root, dest_root, {"PROJECT_NAME": "demo"})

    assert {r.action for r in results} == {WriteAction.WRITTEN}
    assert (dest_root / "a" / "x.md").read_text() == "x for demo\n"
    assert (dest_root / "y.md").read_text() == "y\n"
    assert (dest_root / ".hidden").read_text() == "hidden\n"
