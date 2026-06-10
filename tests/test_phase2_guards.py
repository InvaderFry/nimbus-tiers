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


# ----- context-length preflight ----------------------------------------------


def _extract_max_seq_len_re() -> str:
    """Pull the max_seq_len grep -oE pattern out of phase2.sh."""
    text = PHASE2_PATH.read_text(encoding="utf-8")
    m = re.search(r"grep -oE '(\"max_seq_len\"[^']*)'", text)
    assert m, "max_seq_len extraction pattern not found in phase2.sh"
    return m.group(1)


def test_preflight_enforces_context_length_floor() -> None:
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert "PHASE2_MIN_CTX" in text, "phase2.sh missing PHASE2_MIN_CTX env override"
    assert "/model\"" in text, (
        "preflight should query TabbyAPI's /v1/model endpoint for the model card"
    )
    assert "skipping context-length check" in text, (
        "non-TabbyAPI servers (no /v1/model) must skip the check, not fail"
    )


def test_max_seq_len_pattern_parses_tabbyapi_model_card() -> None:
    regex = _extract_max_seq_len_re()
    tabby_card = (
        '{"id":"Qwen2.5-Coder-14B-Instruct-exl3-6.0bpw","object":"model",'
        '"parameters":{"max_seq_len": 32768,"cache_size":32768}}'
    )
    result = subprocess.run(
        ["grep", "-oE", regex], input=tabby_card, text=True, capture_output=True
    )
    assert result.returncode == 0, "pattern should match a TabbyAPI model card"
    digits = re.sub(r"\D", "", result.stdout.splitlines()[0])
    assert digits == "32768"


def test_max_seq_len_pattern_ignores_foreign_payloads() -> None:
    regex = _extract_max_seq_len_re()
    vllm_models = '{"object":"list","data":[{"id":"foo","max_model_len":8192}]}'
    result = subprocess.run(
        ["grep", "-qE", regex], input=vllm_models, text=True
    )
    assert result.returncode == 1, "pattern must not match non-TabbyAPI payloads"


# ----- automatic fallback model -----------------------------------------------


def test_fallback_model_is_wired_into_aider_invocation() -> None:
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert "PHASE2_FALLBACK_MODEL" in text, "phase2.sh missing PHASE2_FALLBACK_MODEL"
    assert "phase2-fail-step" in text, (
        "fallback requires the per-step failure marker in .git/"
    )
    assert re.search(r"MODEL_OVERRIDE_ARGS=\(--model \"\$PHASE2_FALLBACK_MODEL\"\)", text), (
        "fallback model must be passed to aider via --model"
    )
    assert "MODEL_OVERRIDE_ARGS[@]" in text.split("aider \\")[1], (
        "MODEL_OVERRIDE_ARGS must be expanded in the aider command line"
    )


def test_routing_csv_logs_tier_from_variables_not_literals() -> None:
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert "${_ROUTE_TIER}" in text and "${_ROUTE_ESCALATED_FROM}" in text, (
        "log_routing must interpolate tier/escalated_from so fallback runs are "
        "recorded as tier 2 instead of a hardcoded tier 1"
    )


def test_failure_marker_cleared_on_success_and_halt() -> None:
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert text.count('rm -f "$WIP_FILE" "$FAIL_MARKER"') >= 3, (
        "FAIL_MARKER must be removed on the success path and both halt paths"
    )
