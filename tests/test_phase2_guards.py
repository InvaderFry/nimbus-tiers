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
    """The post-Aider malformed-path guard must check the dotted-JVM-dir pattern.

    The pre-existing guard only matched the literal '**' artifact; neither
    reported failure path contained '**', so they slipped through to a generic
    'planned file missing' rejection. The guard must now also grep the JVM
    package-as-directory pattern and clean up the offending artifacts.
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert "_JVM_DOTTED_DIR_RE" in text, "phase2.sh missing _JVM_DOTTED_DIR_RE definition"
    # Used by both the pre-Aider planned-path skip and the post-Aider guard.
    assert text.count("_JVM_DOTTED_DIR_RE") >= 3, (
        "expected _JVM_DOTTED_DIR_RE to be defined and used in both the pre-Aider "
        "and post-Aider guards"
    )
    assert "package-name-as-directory" in text, (
        "post-Aider guard should explain the package-name-as-directory bug"
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
    """Return True iff `grep -E regex` matches the line, mirroring phase2.sh."""
    result = subprocess.run(
        ["grep", "-qE", regex],
        input=line,
        text=True,
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
