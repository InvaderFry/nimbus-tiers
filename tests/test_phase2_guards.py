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


# ----- bookkeeping ordering and self-blocking guards (0609 failures) -----------


def test_routing_row_is_committed_with_the_step() -> None:
    """log_routing must run BEFORE the commit and the CSV must be staged.

    The 0609 runs appended logs/ai-routing.csv AFTER `git commit`, leaving the
    tree dirty after every 'successful' step — which tripped the next run's
    dirty-tree guard and forced bookkeeping-only commits (the stray 'Step1'
    commit containing nothing but the routing CSV).
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    # Success path: the "done" routing call precedes the step commit.
    done_call = text.index('log_routing "step-${STEP_PAD}" "true"')
    step_commit = text.index('git commit -m "Step $NEXT: complete"')
    assert done_call < step_commit, (
        "success-path log_routing must run before the step commit"
    )
    # Both halt paths and the success path must stage the routing CSV.
    assert text.count('git add -- "$ROUTING_LOG"') >= 3, (
        "the routing CSV must be staged into the step/halt commit on all three "
        "bookkeeping paths"
    )
    # No halt commit may be followed by its routing call: every 'halted' routing
    # call must appear shortly before the halt commit in its block.
    halt_commits = list(re.finditer(re.escape('git commit -m "Step $NEXT: HALT'), text))
    assert len(halt_commits) == 2, "expected the inner and outer halt commit paths"
    for match in halt_commits:
        preceding = text[max(0, match.start() - 600):match.start()]
        assert 'log_routing "step-${STEP_PAD}" "false" "0" "halted"' in preceding, (
            "halt-path log_routing must run before the halt commit"
        )


def test_dirty_tree_guards_ignore_step_logs() -> None:
    """The dirty-tree and recovery-dirty checks must exclude plans/*.log.

    phase2.sh writes preflight WARNs into $LOG_FILE before the dirty-tree
    check. If .gitignore loses its plans/*.log rule (Aider corrupted it in the
    0609 run), every invocation creates an untracked log and then blocks
    itself on it. Using _COMMIT_EXCLUDES (which carries ':!plans/*.log')
    instead of _BUILD_EXCLUDES breaks that self-blocking loop; the logs are
    excluded from the step commit anyway.
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert "DIRTY=$(git status --porcelain -- '.' \"${_COMMIT_EXCLUDES[@]}\"" in text, (
        "startup dirty-tree guard must use _COMMIT_EXCLUDES so step logs never block it"
    )
    assert "_RECOVERY_DIRTY=$(git status --porcelain -- '.' \"${_COMMIT_EXCLUDES[@]}\"" in text, (
        "recovery dirty check must use _COMMIT_EXCLUDES so this run's own log "
        "does not make every recovery look dirty"
    )


def test_gitignore_required_entries_guard_present() -> None:
    """phase2.sh must repair required .gitignore entries after the Aider run.

    The 0609 run saw Aider truncate .gitignore to a partial line; losing
    'plans/*.log' made the executor's own step logs untracked and wedged all
    subsequent runs on the dirty-tree guard.
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert "_repair_gitignore() {" in text, "phase2.sh missing _repair_gitignore"
    assert 'grep -qxF -- "$1" .gitignore' in text, (
        "repair guard must whole-line literal-match each required entry"
    )
    # Negations are order-dependent (last matching rule wins): when the
    # `.aider*` glob is missing, the whole ordered glob+negations block must be
    # re-appended even if the negations survived — appending the glob alone
    # after them would re-ignore both config files.
    assert re.search(
        r"if ! _gitignore_has '\.aider\*'; then\s*\n\s*"
        r"_append\+=\('\.aider\*' '!\.aider\.conf\.yml' '!\.aiderignore'\)",
        text,
    ), "a missing .aider* glob must re-append the full ordered glob+negations block"
    assert "_gitignore_has 'plans/*.log'" in text, (
        "repair guard must cover the plans/*.log rule"
    )


def test_gitignore_repair_runs_before_no_change_guard() -> None:
    """A gitignore-only corruption must still get repaired.

    The no-change guard deliberately excludes .gitignore from its progress
    check and exits 1 when nothing else changed — so a repair placed only
    after that guard never runs when corrupting .gitignore was Aider's sole
    output, leaving the plans/*.log rule lost. The post-Aider repair call must
    precede the guard; the SKIP_AIDER=true recovery path has its own call.
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    calls = [
        m.start()
        for m in re.finditer(r"^[ \t]*_repair_gitignore[ \t]*$", text, flags=re.MULTILINE)
    ]
    assert len(calls) == 2, "expected a post-Aider and a recovery-path repair call"
    no_change_exit = text.index("==> Aider made no changes")
    assert min(calls) < no_change_exit, (
        "the post-Aider repair call must precede the no-change guard's exit"
    )


def test_strict_model_match_gate_is_available() -> None:
    """The served/configured model mismatch must offer an opt-in hard gate.

    Both 0609 failures started under a silently-tolerated model mismatch
    (configured exl3-6.0bpw label vs served exl2 weights). The default stays a
    warning (server id formatting varies), but PHASE2_STRICT_MODEL_MATCH must
    turn the mismatch into an abort for users who want enforcement.
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert "PHASE2_STRICT_MODEL_MATCH" in text, (
        "phase2.sh missing the PHASE2_STRICT_MODEL_MATCH opt-in gate"
    )
    assert "aborting on model mismatch" in text, (
        "strict gate must abort with a clear error when armed"
    )


# ----- exit-code integrity of the generated gate (0609 Java failure) -----------

JAVA_HELPER_PATHS = [
    REPO_ROOT / "templates" / "stacks" / "java-maven" / "PHASE1_VERIFY.md",
    REPO_ROOT / "templates" / "stacks" / "java-gradle" / "PHASE1_VERIFY.md",
]


@pytest.mark.parametrize("helper", JAVA_HELPER_PATHS, ids=["maven", "gradle"])
def test_java_helpers_capture_real_wait_status(helper: Path) -> None:
    """The JVM helpers must not ship the `if ! wait` exit-swallowing pattern.

    `if ! wait "$pid"; then status=$?` reads the status of the NEGATED test
    (always 0) inside the branch, so every build failure reports success. The
    0609 Java run committed a pom.xml with non-resolving coordinates as a
    'passing' step because the generated verify.sh inherited this pattern
    verbatim from the helper. The fix is `wait "$pid" || status=$?`.
    """
    text = helper.read_text(encoding="utf-8")
    # The pattern may legitimately appear in prose/comments warning against it;
    # only an actual code line (statement starting with `if ! wait`) is a bug.
    code_lines = [
        ln for ln in text.splitlines()
        if ln.strip().startswith("if ! wait")
    ]
    assert not code_lines, (
        f"{helper.name} still contains the `if ! wait` exit-swallowing pattern "
        f"as code: {code_lines}"
    )
    assert re.search(r'wait "\$\w+_pid" \|\| \w+_status=\$\?', text), (
        f"{helper.name} must capture wait's real status via `|| status=$?`"
    )


def _extract_gate_lint_re() -> str:
    text = PHASE2_PATH.read_text(encoding="utf-8")
    m = re.search(r"grep -qE '([^']*wait[^']*)' verify\.sh", text)
    assert m, "gate-integrity lint pattern not found in phase2.sh"
    return m.group(1)


def test_gate_lint_rejects_exit_swallowing_verify() -> None:
    """phase2.sh must refuse to run a verify.sh containing `if ! wait`.

    Already-generated projects keep their buggy verify.sh even after the
    helper templates are fixed; the lint stops them from recording false
    DONEs until the gate is repaired.
    """
    regex = _extract_gate_lint_re()
    assert _grep_matches(regex, 'if ! wait "$mvn_pid"; then'), (
        "lint must match the buggy `if ! wait` pattern"
    )
    assert _grep_matches(regex, '  if ! wait "$gradle_pid"; then'), (
        "lint must match the buggy pattern on an indented code line"
    )
    assert not _grep_matches(regex, 'wait "$mvn_pid" || mvn_status=$?'), (
        "lint must not flag the correct `wait || status=$?` capture"
    )
    # The fixed JVM helpers warn against the pattern in bash comments that a
    # correctly generated verify.sh copies verbatim. The lint is anchored to
    # the start of an executable line so the good gate is not rejected.
    assert not _grep_matches(
        regex,
        '  # Capture wait\'s REAL exit status. Do NOT write `if ! wait "$pid"; then',
    ), "lint must not flag the helper's warning comment"


# ----- build-file coordinate corruption (0609 Java step01) ----------------------


def _extract_coord_corruption_re() -> str:
    text = PHASE2_PATH.read_text(encoding="utf-8")
    m = re.search(r"^_BUILD_COORD_CORRUPTION_RE='([^']*)'", text, flags=re.MULTILINE)
    assert m, "_BUILD_COORD_CORRUPTION_RE assignment not found in phase2.sh"
    return m.group(1)


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
def test_coord_guard_flags_corrupted_coordinates(line: str) -> None:
    regex = _extract_coord_corruption_re()
    assert _grep_matches(regex, line), f"guard should flag corrupted coordinate: {line!r}"


@pytest.mark.parametrize("line", VALID_COORDS)
def test_coord_guard_allows_valid_coordinates(line: str) -> None:
    regex = _extract_coord_corruption_re()
    assert not _grep_matches(regex, line), f"guard must not flag valid coordinate: {line!r}"


def test_build_files_are_never_whole_safe() -> None:
    """Existing build files must force diff edit format.

    The 0609 corruption happened because the 40-line scaffold pom.xml was
    under the whole-file threshold, so the model regenerated the ENTIRE file
    — re-emitting (and mangling) every coordinate. Diff edits only touch the
    lines the step adds.
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    assert "pom.xml|build.gradle|build.gradle.kts|settings.gradle|settings.gradle.kts" in text, (
        "whole-format safety check must special-case JVM build files"
    )
    assert "Existing build file" in text and "diff edit format" in text, (
        "the build-file diff fallback must be reported in the step log"
    )


def test_malformed_path_cleanup_unstages_first() -> None:
    """Both discard-and-reset cleanups must `git reset` before checkout/clean.

    Aider stages new files it creates; `git checkout -- .` restores them from
    the index and `git clean -fd` skips index-tracked paths, so without the
    reset the staged malformed files survive cleanup and wedge later runs
    (observed after the 0609 step02 rejection).
    """
    text = PHASE2_PATH.read_text(encoding="utf-8")
    for marker in ("Discarding malformed files", "Discarding this run's changes"):
        idx = text.index(marker)
        block = text[idx:idx + 700]
        # Match the full command lines (with redirection) so the in-code
        # comment that *mentions* `git checkout -- .` is not counted.
        reset = block.find("git reset -q HEAD -- . 2>/dev/null")
        checkout = block.find("git checkout -- . 2>/dev/null")
        assert 0 <= reset < checkout, (
            f"cleanup after {marker!r} must unstage (git reset) before git checkout/clean"
        )


# ----- python verify.sh helper --------------------------------------------------

PY_HELPER_PATH = REPO_ROOT / "templates" / "stacks" / "python" / "PHASE1_VERIFY.md"


def test_python_verify_helper_fails_hard_on_missing_venv() -> None:
    """The Python helper must make a missing .venv a non-zero failure.

    The 0609 generated verify.sh exited 0 when .venv was absent, so phase2.sh
    recorded Step 1 DONE without running a single test. The helper must ship a
    require_venv gate that exits 1 with remediation, and must say the exit-0
    allowance is for a missing sentinel only.
    """
    text = PY_HELPER_PATH.read_text(encoding="utf-8")
    assert "require_venv()" in text, "helper missing the require_venv gate"
    assert 'if [ ! -f ".venv/bin/activate" ]' in text
    assert "exit 1" in text, "missing .venv must exit non-zero"
    assert "python3 -m venv .venv" in text, "remediation command must be printed"
    assert "non-zero" in text and "sentinel" in text, (
        "helper must scope the exit-0 allowance to a missing sentinel only"
    )
