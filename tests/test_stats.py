"""Tests for nimbus-stats (routing-log analyzer)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nimbus_tiers.stats.cli import main as stats_main

HEADER = (
    "date,repo,task_type,tier_used,model,escalated_from,tests_passed,"
    "diff_lines_approx,human_rework_minutes,outcome"
)

SAMPLE_ROWS = [
    "2026-06-01T10:00:00Z,demo,step-01,1,local,,true,40,,done",
    "2026-06-01T11:00:00Z,demo,step-02,1,local,,true,60,,done",
    "2026-06-02T09:00:00Z,demo,step-03,2,groq/llama-3.3-70b-versatile,local,true,120,,done",
    "2026-06-03T09:00:00Z,demo,step-04,1,local,,false,0,,halted",
]


def _write_log(tmp_path: Path, lines: list[str]) -> Path:
    log = tmp_path / "ai-routing.csv"
    log.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return log


def test_summary_reports_tiers_escalations_and_outcomes(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    log = _write_log(tmp_path, [HEADER, *SAMPLE_ROWS])
    assert stats_main(["--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "4 step run(s)" in out
    assert "done: 3" in out and "halted: 1" in out
    assert "tier 1: 3 (75%)" in out
    assert "tier 2: 1 (25%)" in out
    assert "1 of 4 (25%)" in out  # escalation rate
    assert "groq/llama-3.3-70b-versatile: 1" in out
    assert "total 220" in out and "max 120" in out
    assert "2026-06-01T10:00:00Z .. 2026-06-03T09:00:00Z" in out
    # The honest-limitation footer must always be present.
    assert "failed runs are not logged" in out


def test_malformed_rows_are_skipped_and_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    log = _write_log(tmp_path, [HEADER, SAMPLE_ROWS[0], "2026-06-01T12:00:00Z,demo"])
    assert stats_main(["--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "1 step run(s)" in out
    assert "1 malformed row(s) skipped" in out


def test_missing_file_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert stats_main(["--log", str(tmp_path / "nope.csv")]) == 1
    assert "not found" in capsys.readouterr().err


def test_header_only_file_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    log = _write_log(tmp_path, [HEADER])
    assert stats_main(["--log", str(log)]) == 1
    assert "no data rows" in capsys.readouterr().err


def test_garbage_file_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    log = _write_log(tmp_path, ["this is not a routing log"])
    assert stats_main(["--log", str(log)]) == 1
    assert "no parseable header" in capsys.readouterr().err


def test_empty_file_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    log = _write_log(tmp_path, [])
    assert stats_main(["--log", str(log)]) == 1


def test_header_matches_phase2_routing_header() -> None:
    """The analyzer's expected schema must stay in sync with phase2.sh."""
    from nimbus_tiers.resources import templates_root
    from nimbus_tiers.stats.cli import EXPECTED_COLUMNS

    phase2 = (templates_root() / "phase2.sh").read_text(encoding="utf-8")
    assert f'ROUTING_HEADER="{",".join(EXPECTED_COLUMNS)}"' in phase2, (
        "EXPECTED_COLUMNS drifted from phase2.sh's ROUTING_HEADER"
    )
