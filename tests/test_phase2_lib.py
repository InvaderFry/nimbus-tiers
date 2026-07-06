"""Unit tests for phase2-lib.sh — the sourceable pure-helper library.

Each test invokes a lib function directly via `bash -c 'source ...; fn args'`,
so the guard logic is exercised as real code rather than by regex-scraping
phase2.sh's text (the pre-extraction approach). Wiring assertions — that
phase2.sh actually *calls* these helpers in the right places — stay in
test_phase2_guards.py.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

from nimbus_tiers.resources import templates_root

LIB_PATH = templates_root() / "phase2-lib.sh"


def _lib(snippet: str, cwd: Path | None = None, stdin: str = "") -> subprocess.CompletedProcess:
    """Source the lib and run a snippet; returns the completed process."""
    return subprocess.run(
        ["bash", "-c", f"set -euo pipefail; source '{LIB_PATH}'; {snippet}"],
        capture_output=True,
        text=True,
        input=stdin,
        cwd=cwd,
    )


def _lib_out(snippet: str, cwd: Path | None = None, stdin: str = "") -> str:
    proc = _lib(snippet, cwd=cwd, stdin=stdin)
    assert proc.returncode == 0, f"lib call failed: {proc.stderr}"
    return proc.stdout


def _lib_rc(snippet: str, cwd: Path | None = None) -> int:
    # `set -e` would kill the shell on the first failing check; disable it for
    # exit-code probes.
    proc = subprocess.run(
        ["bash", "-c", f"source '{LIB_PATH}'; {snippet}"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return proc.returncode


# ---------------------------------------------------------------------------
# _strip_md_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry,expected", [
    ("- src/Foo.java", "src/Foo.java"),
    ("-  src/Foo.java", "src/Foo.java"),  # double-space typo
    ("- `src/Foo.java`", "src/Foo.java"),
    ('- "src/Foo.java"', "src/Foo.java"),
    ("- 'src/Foo.java'", "src/Foo.java"),
    ("- src/Foo.java (new file)", "src/Foo.java"),
    ("- com/example(v1)/Foo.java", "com/example(v1)/Foo.java"),  # ( in dir kept
    ("- src/Foo.java   ", "src/Foo.java"),  # trailing whitespace
])
def test_strip_md_path(entry: str, expected: str) -> None:
    out = _lib_out(f"_strip_md_path {shlex.quote(entry)}")
    assert out == expected


# ---------------------------------------------------------------------------
# nimbus_planned_entries
# ---------------------------------------------------------------------------


def test_planned_entries_extracts_only_files_section(tmp_path: Path) -> None:
    step = tmp_path / "step01.md"
    step.write_text(
        "# Step 1\n"
        "## Goal\n- not a file\n"
        "## Files to change\n- src/a.py\n- src/b.py\nprose line\n"
        "## Verify\n- not-this.py\n",
        encoding="utf-8",
    )
    out = _lib_out(f"nimbus_planned_entries '{step}'")
    assert out.splitlines() == ["- src/a.py", "- src/b.py"]


def test_planned_entries_empty_when_section_missing(tmp_path: Path) -> None:
    step = tmp_path / "step01.md"
    step.write_text("# Step 1\n## Goal\n- x\n", encoding="utf-8")
    assert _lib_out(f"nimbus_planned_entries '{step}'") == ""


# ---------------------------------------------------------------------------
# nimbus_is_malformed_jvm_path (ported from the regex-scrape tests)
# ---------------------------------------------------------------------------


MALFORMED = [
    "src/main/java/com.example/app0501/Foo.java",
    "src/main/java(com.example.app0501)/Foo.java",
    " M src/test/java/com.example/Bar.java",
    "?? src/main/kotlin/com.acme/X.kt",
    "?? src/main/java/com.example/",
]

VALID = [
    "src/main/java/com/example/app0501/Foo.java",
    " M src/test/java/com/example/app0501/FooTest.java",
    "src/main/resources/application.properties",
    "pom.xml",
    "src/main/java/com/example/Foo.Bar.java",  # dotted filename, not a dir
    "?? src/main/java/com/example/app0501/",
]


@pytest.mark.parametrize("path", MALFORMED)
def test_malformed_jvm_paths_flagged(path: str) -> None:
    assert _lib_rc(f"nimbus_is_malformed_jvm_path '{path}'") == 0


@pytest.mark.parametrize("path", VALID)
def test_valid_jvm_paths_allowed(path: str) -> None:
    assert _lib_rc(f"nimbus_is_malformed_jvm_path '{path}'") == 1


# ---------------------------------------------------------------------------
# build-file guards (ported from the regex-scrape tests)
# ---------------------------------------------------------------------------


CORRUPTED_COORDS = [
    "<artifactId>spring-boot-starters-parent</artifactId>",
    "<artifactId>spring-boot-started-web</artifactId>",
    'implementation "org.springframework.boot:spring-boot-started-test"',
]

VALID_COORDS = [
    "<artifactId>spring-boot-starter-parent</artifactId>",
    "<artifactId>spring-boot-starter-web</artifactId>",
    "<artifactId>spring-boot-starter-test</artifactId>",
    "<artifactId>spring-boot-starter</artifactId>",
    "<artifactId>spring-boot-maven-plugin</artifactId>",
]


@pytest.mark.parametrize("line", CORRUPTED_COORDS)
def test_corrupt_coordinates_flagged(tmp_path: Path, line: str) -> None:
    build = tmp_path / "pom.xml"
    build.write_text(line + "\n", encoding="utf-8")
    assert _lib_rc(f"nimbus_has_corrupt_build_coords '{build}'") == 0


@pytest.mark.parametrize("line", VALID_COORDS)
def test_valid_coordinates_allowed(tmp_path: Path, line: str) -> None:
    build = tmp_path / "pom.xml"
    build.write_text(line + "\n", encoding="utf-8")
    assert _lib_rc(f"nimbus_has_corrupt_build_coords '{build}'") == 1


@pytest.mark.parametrize("name,is_build", [
    ("pom.xml", True),
    ("build.gradle", True),
    ("build.gradle.kts", True),
    ("settings.gradle", True),
    ("settings.gradle.kts", True),
    ("some/dir/pom.xml", True),
    ("main.py", False),
    ("pom.xml.bak", False),
    ("mypom.xml", False),
])
def test_is_build_file(name: str, is_build: bool) -> None:
    assert (_lib_rc(f"nimbus_is_build_file '{name}'") == 0) is is_build


# ---------------------------------------------------------------------------
# gate lint (ported from _extract_gate_lint_re tests)
# ---------------------------------------------------------------------------


def _gate_rc(tmp_path: Path, content: str) -> int:
    gate = tmp_path / "verify.sh"
    gate.write_text(content, encoding="utf-8")
    return _lib_rc(f"nimbus_gate_swallows_exit '{gate}'")


def test_gate_lint_rejects_exit_swallowing(tmp_path: Path) -> None:
    assert _gate_rc(tmp_path, 'if ! wait "$mvn_pid"; then\n') == 0
    assert _gate_rc(tmp_path, '  if ! wait "$gradle_pid"; then\n') == 0


def test_gate_lint_accepts_correct_status_capture(tmp_path: Path) -> None:
    assert _gate_rc(tmp_path, 'wait "$mvn_pid" || mvn_status=$?\n') == 1


def test_gate_lint_ignores_warning_comment(tmp_path: Path) -> None:
    # The fixed JVM helpers warn against the pattern in comments a correct
    # verify.sh copies verbatim; the lint is anchored to executable lines.
    assert _gate_rc(
        tmp_path,
        '  # Capture wait\'s REAL exit status. Do NOT write `if ! wait "$pid"; then\n',
    ) == 1


# ---------------------------------------------------------------------------
# .aider.conf.yml scalar reader / model-card parsing
# ---------------------------------------------------------------------------


def test_read_aider_conf_scalar(tmp_path: Path) -> None:
    conf = tmp_path / ".aider.conf.yml"
    conf.write_text(
        'model: openai/foo\nopenai-api-base: "http://localhost:5000/v1"\n',
        encoding="utf-8",
    )
    assert _lib_out("_read_aider_conf_scalar model", cwd=tmp_path) == "openai/foo\n"
    assert (
        _lib_out("_read_aider_conf_scalar openai-api-base", cwd=tmp_path)
        == "http://localhost:5000/v1\n"
    )
    assert _lib_out("_read_aider_conf_scalar missing-key", cwd=tmp_path) == ""


def test_read_aider_conf_scalar_missing_file(tmp_path: Path) -> None:
    assert _lib_out("_read_aider_conf_scalar model", cwd=tmp_path) == ""


def test_max_seq_len_parses_tabbyapi_model_card() -> None:
    tabby_card = (
        '{"id":"Qwen2.5-Coder-14B-Instruct-exl3-6.0bpw","object":"model",'
        '"parameters":{"max_seq_len": 32768,"cache_size":32768}}'
    )
    assert _lib_out("nimbus_max_seq_len", stdin=tabby_card) == "32768"


def test_max_seq_len_ignores_foreign_payloads() -> None:
    vllm_models = '{"object":"list","data":[{"id":"foo","max_model_len":8192}]}'
    assert _lib_out("nimbus_max_seq_len", stdin=vllm_models) == ""


# ---------------------------------------------------------------------------
# .gitignore repair computation
# ---------------------------------------------------------------------------

REQUIRED_BLOCK = [".aider*", "!.aider.conf.yml", "!.aiderignore"]


def _missing(tmp_path: Path, content: str) -> list[str]:
    gi = tmp_path / ".gitignore"
    gi.write_text(content, encoding="utf-8")
    return _lib_out(f"nimbus_missing_gitignore_entries '{gi}'").splitlines()


def test_gitignore_intact_reports_nothing(tmp_path: Path) -> None:
    content = "\n".join(REQUIRED_BLOCK + ["plans/*.log"]) + "\n"
    assert _missing(tmp_path, content) == []


def test_gitignore_empty_reports_full_ordered_block(tmp_path: Path) -> None:
    assert _missing(tmp_path, "") == REQUIRED_BLOCK + ["plans/*.log"]


def test_gitignore_missing_glob_reappends_whole_block(tmp_path: Path) -> None:
    # Negations survived but the glob is gone: the ordered block must be
    # re-emitted in full — appending the glob alone after the negations would
    # re-ignore both config files (last matching rule wins).
    content = "!.aider.conf.yml\n!.aiderignore\nplans/*.log\n"
    assert _missing(tmp_path, content) == REQUIRED_BLOCK


def test_gitignore_missing_single_negation(tmp_path: Path) -> None:
    content = ".aider*\n!.aider.conf.yml\nplans/*.log\n"
    assert _missing(tmp_path, content) == ["!.aiderignore"]


def test_gitignore_commented_entry_counts_as_missing(tmp_path: Path) -> None:
    content = ".aider*\n!.aider.conf.yml\n!.aiderignore\n# plans/*.log\n"
    assert _missing(tmp_path, content) == ["plans/*.log"]


# ---------------------------------------------------------------------------
# log classifiers
# ---------------------------------------------------------------------------


def test_log_input_overflow_detection(tmp_path: Path) -> None:
    log = tmp_path / "step.log"
    log.write_text("blah\nERROR: maximum context length is 10000 tokens\n", encoding="utf-8")
    assert _lib_rc(f"nimbus_log_input_overflow '{log}'") == 0
    log.write_text("clean run\n", encoding="utf-8")
    assert _lib_rc(f"nimbus_log_input_overflow '{log}'") == 1


def test_log_token_limit_detection(tmp_path: Path) -> None:
    log = tmp_path / "step.log"
    log.write_text("Model has hit a token limit!\n", encoding="utf-8")
    assert _lib_rc(f"nimbus_log_token_limit '{log}'") == 0
    log.write_text("finish_reason: length\n", encoding="utf-8")
    assert _lib_rc(f"nimbus_log_token_limit '{log}'") == 0
    log.write_text("finish_reason: stop\n", encoding="utf-8")
    assert _lib_rc(f"nimbus_log_token_limit '{log}'") == 1


def test_log_max_repeat_counts_consecutive_runs_only(tmp_path: Path) -> None:
    log = tmp_path / "step.log"
    repeated = "import com.example.app.Foo;\n"
    # 5 consecutive repeats, then interleaved recurrences that would fool a
    # total-occurrence count.
    log.write_text(
        repeated * 5 + ("some other long line here\n" + repeated) * 10,
        encoding="utf-8",
    )
    assert _lib_out(f"nimbus_log_max_repeat '{log}'").strip() == "5"


def test_log_max_repeat_ignores_trivial_lines(tmp_path: Path) -> None:
    log = tmp_path / "step.log"
    log.write_text("}\n" * 100, encoding="utf-8")  # short lines never count
    assert _lib_out(f"nimbus_log_max_repeat '{log}'").strip() == "0"


def test_log_max_repeat_strips_trailing_padding(tmp_path: Path) -> None:
    # Aider pads lines to terminal width: "+" plus spaces must stay trivial.
    log = tmp_path / "step.log"
    log.write_text(("+" + " " * 40 + "\n") * 50, encoding="utf-8")
    assert _lib_out(f"nimbus_log_max_repeat '{log}'").strip() == "0"


def test_log_max_total_repeat_counts_interleaved(tmp_path: Path) -> None:
    log = tmp_path / "step.log"
    repeated = "import com.example.app.Foo;\n"
    log.write_text(("a much longer separator line\n" + repeated) * 7, encoding="utf-8")
    assert _lib_out(f"nimbus_log_max_total_repeat '{log}'").strip() == "7"


# ---------------------------------------------------------------------------
# step counter
# ---------------------------------------------------------------------------


def test_next_step_without_completed_file(tmp_path: Path) -> None:
    assert _lib_out("nimbus_next_step", cwd=tmp_path).strip() == "1"


def test_next_step_skips_done_steps(tmp_path: Path) -> None:
    (tmp_path / "CompletedSteps.md").write_text(
        "# Completed Steps\nStep 1: DONE\nStep 2: DONE\nStep 4: DONE\n",
        encoding="utf-8",
    )
    assert _lib_out("nimbus_next_step", cwd=tmp_path).strip() == "3"
