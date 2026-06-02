"""Tests guarding phase2.sh runtime guards (the malformed-path detector)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE2_PATH = REPO_ROOT / "templates" / "phase2.sh"


def _extract_jvm_dotted_dir_re() -> str:
    """Pull the single-quoted _JVM_DOTTED_DIR_RE value out of phase2.sh.

    Testing the real regex string (rather than a copy) means this test fails if
    the script's pattern drifts away from the behavior asserted below.
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    m = re.search(r"^_JVM_DOTTED_DIR_RE='([^']*)'", text, flags=re.MULTILINE)
    assert m, "_JVM_DOTTED_DIR_RE assignment not found in phase2.sh"
    return m.group(1)


def test_malformed_path_guard_covers_dotted_jvm_dirs() -> None:
    """The malformed-path pattern must be wired into BOTH guards.

    The pre-existing guard only matched the literal '**' artifact; neither
    reported failure path contained '**', so they slipped through to a generic
    'planned file missing' rejection. Both arms must now use the JVM
    package-as-directory pattern. Rather than count occurrences (brittle to
    benign refactors), assert each arm by its distinct, behavior-bearing text:
    the pre-Aider arm's per-path WARN and the post-Aider arm's explanation.
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert re.search(r"^_JVM_DOTTED_DIR_RE=", text, flags=re.MULTILINE), (
        "phase2.sh missing _JVM_DOTTED_DIR_RE definition"
    )
    # Pre-Aider planned-path skip.
    assert "skipping planned path with a dotted/parenthesised directory" in text, (
        "pre-Aider guard should skip malformed planned paths with a clear WARN"
    )
    # Post-Aider working-tree guard.
    assert "package-name-as-directory" in text, (
        "post-Aider guard should explain the package-name-as-directory bug"
    )
    # The post-Aider guard must expand untracked dirs, or it misses a malformed
    # dir created in a greenfield step (porcelain collapses '?? src/').
    assert "--untracked-files=all" in text, (
        "post-Aider guard must use --untracked-files=all so a greenfield "
        "malformed dir is not hidden by porcelain's untracked-tree collapse"
    )


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


def _grep_matches(regex: str, line: str) -> bool:
    """Return True iff `grep -E regex` matches the line, mirroring phase2.sh.

    grep returns 0 on match, 1 on no-match, and >=2 on error (e.g. an invalid
    ERE). Treat rc 2 as a hard failure rather than silently folding it into
    "no match" — otherwise a broken pattern would pass the VALID-path tests.
    """
    result = subprocess.run(
        ["grep", "-qE", regex],
        input=line,
        text=True,
    )
    assert result.returncode in (0, 1), (
        f"grep errored (rc={result.returncode}) on regex {regex!r} — invalid ERE?"
    )
    return result.returncode == 0


@pytest.mark.parametrize("path", MALFORMED)
def test_regex_flags_malformed_jvm_paths(path: str) -> None:
    regex = _extract_jvm_dotted_dir_re()
    assert _grep_matches(regex, path), f"guard should flag malformed path: {path!r}"


@pytest.mark.parametrize("path", VALID)
def test_regex_allows_valid_paths(path: str) -> None:
    regex = _extract_jvm_dotted_dir_re()
    assert not _grep_matches(regex, path), f"guard should not flag valid path: {path!r}"
