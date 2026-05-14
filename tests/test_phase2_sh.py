"""Integration tests for templates/phase2.sh.

Each test creates a minimal git repository in a temp directory, installs a
controllable stub 'aider' script on PATH, then verifies phase2.sh's exit code
and repo state. No real Aider or model is involved.

Coverage targets:
  - no step files → exits 0, prints "Run Phase 1 first"
  - missing verify.sh → exits 1 with clear error  (fix #4)
  - non-executable verify.sh → exits 1 with clear error  (fix #4)
  - successful step: stub makes a change, verify passes → exits 0, DONE recorded
  - empty diff: stub exits 0 but writes nothing → exits 1 (model-not-reached guard)
  - halt file written by stub → exits 2, only halt file committed
  - aider exits non-zero → phase2.sh exits that code, step not recorded
  - all steps done, non-interactive session → exits 0 with "Non-interactive" skip
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

PHASE2_SH = Path(__file__).parent.parent / "templates" / "phase2.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="bash not on PATH",
)

# ── git helpers ───────────────────────────────────────────────────────────────

_GIT_ID = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ID},
    )


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Minimal git repo pre-wired for phase2.sh.

    Committed layout:
      phase2.sh          (executable copy of templates/phase2.sh)
      CONTEXT.md         (required by aider --read CONTEXT.md)
      output.txt         (a tracked file stubs can modify to trigger the diff guard)
      verify.sh          (exits 0, executable)
      plans/step01.md    (minimal step file with required sections)
      logs/ai-routing.csv (header only)
      .gitignore         (excludes .test_bin/ and plans/*.log)
    """
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "gpg.format", "openpgp")

    (tmp_path / "plans").mkdir()
    (tmp_path / "logs").mkdir()

    # phase2.sh
    p2 = tmp_path / "phase2.sh"
    shutil.copy(PHASE2_SH, p2)
    p2.chmod(p2.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

    # CONTEXT.md (referenced by --read in phase2.sh's aider invocation)
    (tmp_path / "CONTEXT.md").write_text("# Context\nNo constraints.\n")

    # Stack sentinel so phase2.sh's sentinel-guard doesn't emit a WARN
    (tmp_path / "requirements.txt").write_text("# stub\n")

    # A tracked file stubs can modify to satisfy the empty-diff guard
    (tmp_path / "output.txt").write_text("original\n")

    # verify.sh — exits 0
    _write_verify(tmp_path, exit_code=0)

    # Step file with the three required sections
    (tmp_path / "plans" / "step01.md").write_text(
        "## Goal\nWrite 'hello' to output.txt.\n\n"
        "## Files to change\n- output.txt\n\n"
        "## Done condition\noutput.txt contains 'hello'.\n"
    )

    # Routing log header
    (tmp_path / "logs" / "ai-routing.csv").write_text(
        "date,repo,task_type,tier_used,model,escalated_from,"
        "tests_passed,diff_lines_approx,human_rework_minutes,outcome\n"
    )

    # .gitignore keeps the stub bin dir and log files out of commits
    (tmp_path / ".gitignore").write_text(".test_bin/\nplans/*.log\n")

    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "initial", "--no-gpg-sign")

    return tmp_path


def _write_verify(repo: Path, exit_code: int = 0) -> None:
    v = repo / "verify.sh"
    v.write_text(f"#!/usr/bin/env bash\nexit {exit_code}\n")
    v.chmod(v.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


# ── test runner ───────────────────────────────────────────────────────────────

def _run(repo: Path, stub_body: str = 'exit 0') -> subprocess.CompletedProcess:
    """Run phase2.sh with a stub aider on PATH, no real model involved."""
    bin_dir = repo / ".test_bin"
    bin_dir.mkdir(exist_ok=True)

    stub = bin_dir / "aider"
    stub.write_text(f"#!/usr/bin/env bash\n{stub_body}\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

    env = {
        **os.environ,
        **_GIT_ID,
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        # Disable commit signing in the test repo via env-level git config
        # (overrides global config; requires git >= 2.32).
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
    }
    # Suppress preflight: if inherited AIDER_MODEL is set it may trigger the
    # preflight key checks. Unset it; with no .aider.conf.yml the preflight
    # block is skipped entirely.
    env.pop("AIDER_MODEL", None)

    return subprocess.run(
        ["bash", "phase2.sh"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_no_step_files_exits_0(repo: Path) -> None:
    """When plans/step01.md is absent, phase2.sh prints a hint and exits 0."""
    (repo / "plans" / "step01.md").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "remove step01", "--no-gpg-sign")

    result = _run(repo)

    assert result.returncode == 0
    assert "Run Phase 1 first" in result.stdout


def test_missing_verify_sh_exits_1(repo: Path) -> None:
    """phase2.sh must fail fast when verify.sh is absent (fix #4)."""
    (repo / "verify.sh").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "remove verify.sh", "--no-gpg-sign")

    result = _run(repo)

    assert result.returncode == 1
    assert "verify.sh not found" in result.stderr


def test_non_executable_verify_sh_exits_1(repo: Path) -> None:
    """phase2.sh must fail fast when verify.sh exists but is not executable (fix #4)."""
    v = repo / "verify.sh"
    v.chmod(v.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

    result = _run(repo)

    assert result.returncode == 1
    assert "not executable" in result.stderr


def test_successful_step_records_done(repo: Path) -> None:
    """Successful aider run exits 0, records DONE in CompletedSteps.md, commits."""
    # Stub aider modifies a tracked file so the diff guard passes
    result = _run(repo, stub_body='printf "hello\\n" > output.txt; exit 0')

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Step 1: DONE" in (repo / "CompletedSteps.md").read_text()

    # The commit should include the changed file
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=repo, capture_output=True, text=True,
        env={**os.environ, **_GIT_ID},
    )
    assert "Step 1: complete" in log.stdout


def test_empty_diff_exits_1(repo: Path) -> None:
    """Stub exits 0 but writes nothing → model was not reached → exit 1."""
    result = _run(repo, stub_body='exit 0')

    assert result.returncode == 1
    assert "Aider made no changes" in result.stdout
    # Step must NOT be recorded
    completed = repo / "CompletedSteps.md"
    assert not completed.exists() or "DONE" not in completed.read_text()


def test_halt_file_exits_2_and_commits_only_halt(repo: Path) -> None:
    """When stub writes plans/halt-step01.md, phase2.sh exits 2.

    The halt file is committed; any other changes from the same run are
    discarded so the repo stays clean.
    """
    stub = (
        'printf "halt contents\\n" > plans/halt-step01.md\n'
        'printf "should-be-discarded\\n" > output.txt\n'
        'exit 0'
    )
    result = _run(repo, stub_body=stub)

    assert result.returncode == 2
    assert (repo / "plans" / "halt-step01.md").exists()

    # output.txt must be restored to its original content
    assert (repo / "output.txt").read_text() == "original\n"

    # Step must NOT be recorded as DONE
    completed = repo / "CompletedSteps.md"
    assert not completed.exists() or "DONE" not in completed.read_text()


def test_aider_failure_exits_aider_code(repo: Path) -> None:
    """Non-zero aider exit propagates; step is not recorded."""
    result = _run(repo, stub_body='exit 3')

    assert result.returncode == 3
    completed = repo / "CompletedSteps.md"
    assert not completed.exists() or "DONE" not in completed.read_text()


def test_all_steps_done_non_interactive_exits_0(repo: Path) -> None:
    """All steps DONE + no step02.md + non-interactive stdin → exits 0, skips archive."""
    # Mark step 1 as complete in CompletedSteps.md and commit it
    (repo / "CompletedSteps.md").write_text("# Completed Steps\nStep 1: DONE\n")
    # Remove step file so phase2.sh sees all done
    (repo / "plans" / "step01.md").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "mark done", "--no-gpg-sign")

    result = _run(repo)

    assert result.returncode == 0
    assert "Non-interactive" in result.stdout or "All steps complete" in result.stdout
