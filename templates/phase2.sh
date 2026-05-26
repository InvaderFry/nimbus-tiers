#!/usr/bin/env bash
# Phase 2 executor — runs one Aider step at a time against the local model.
# Re-run until all steps are complete; picks up where it left off via CompletedSteps.md.
# Usage: ./phase2.sh
#
# Exit codes:
#   0  step recorded DONE (or all steps complete; archive performed)
#   1  Aider failure, empty diff, or verify.sh failed — step not recorded
#   2  step halted intentionally (plans/halt-stepNN.md written) — review halt report
set -euo pipefail

# Single-run guard: prevent concurrent phase2.sh executions in the same repo.
# A second run can race bookkeeping and produce confusing sentinel recovery.
LOCK_DIR=".git/phase2.lock"
LOCK_PID_FILE="${LOCK_DIR}/pid"
LOCK_START_FILE="${LOCK_DIR}/starttime"
get_proc_start_time() {
    # Linux procfs start time (clock ticks since boot), field 22 in /proc/<pid>/stat.
    # Empty output means unavailable (non-Linux, vanished process, or inaccessible procfs).
    local pid="$1"
    [ -r "/proc/${pid}/stat" ] || return 1
    awk '{print $22}' "/proc/${pid}/stat" 2>/dev/null || return 1
}
if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$LOCK_PID_FILE"
    get_proc_start_time "$$" > "$LOCK_START_FILE" 2>/dev/null || true
else
    LOCK_OWNER_PID=""
    LOCK_OWNER_START=""
    CURRENT_OWNER_START=""
    if [ -f "$LOCK_PID_FILE" ]; then
        LOCK_OWNER_PID=$(tr -cd '0-9' < "$LOCK_PID_FILE" 2>/dev/null || true)
    fi
    if [ -f "$LOCK_START_FILE" ]; then
        LOCK_OWNER_START=$(tr -cd '0-9' < "$LOCK_START_FILE" 2>/dev/null || true)
    fi
    if [ -n "$LOCK_OWNER_PID" ]; then
        CURRENT_OWNER_START=$(get_proc_start_time "$LOCK_OWNER_PID" 2>/dev/null || true)
    fi

    # Auto-recover stale lock when owner PID is gone or does not match recorded starttime
    # (PID reuse after crash). If starttime is unavailable, fallback to PID liveness only.
    STALE_LOCK=false
    if [ -n "$LOCK_OWNER_PID" ]; then
        if ! kill -0 "$LOCK_OWNER_PID" 2>/dev/null; then
            STALE_LOCK=true
            echo "==> Recovering stale phase2 lock from dead PID ${LOCK_OWNER_PID}."
        elif [ -n "$LOCK_OWNER_START" ] && [ -n "$CURRENT_OWNER_START" ] && [ "$LOCK_OWNER_START" != "$CURRENT_OWNER_START" ]; then
            STALE_LOCK=true
            echo "==> Recovering stale phase2 lock from reused PID ${LOCK_OWNER_PID} (starttime mismatch)."
        fi
    fi

    if [ "$STALE_LOCK" = true ]; then
        rm -f "$LOCK_PID_FILE" 2>/dev/null || true
        rm -f "$LOCK_START_FILE" 2>/dev/null || true
        rmdir "$LOCK_DIR" 2>/dev/null || true
        if mkdir "$LOCK_DIR" 2>/dev/null; then
            printf '%s\n' "$$" > "$LOCK_PID_FILE"
            get_proc_start_time "$$" > "$LOCK_START_FILE" 2>/dev/null || true
        else
            # A concurrent run won the re-acquire; treat that as an active run.
            echo "ERROR: another phase2.sh run acquired the lock during stale recovery."
            exit 1
        fi
    else
        echo "ERROR: another phase2.sh run is already active for this repository."
        if [ -n "$LOCK_OWNER_PID" ]; then
            echo "Lock owner PID: $LOCK_OWNER_PID"
        fi
        echo "If that run crashed, remove $LOCK_DIR and retry."
        exit 1
    fi
fi
cleanup_lock() {
    rm -f "$LOCK_PID_FILE" 2>/dev/null || true
    rm -f "$LOCK_START_FILE" 2>/dev/null || true
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
_AIDER_SUBSHELL=""
_PREFLIGHT_SUBSHELL=""
_handle_signal() {
    cleanup_lock
    # kill -KILL on the subshell process only; children (aider, tee, verify.sh)
    # inside it are NOT forwarded the signal — they survive until kill -KILL 0
    # kills the entire process group on the next line.
    # Running pipelines via background subshells + `wait` makes this trap fire
    # immediately on Ctrl+C instead of being deferred until the pipeline exits.
    [ -n "${_PREFLIGHT_SUBSHELL:-}" ] && kill -KILL "$_PREFLIGHT_SUBSHELL" 2>/dev/null || true
    [ -n "${_AIDER_SUBSHELL:-}" ] && kill -KILL "$_AIDER_SUBSHELL" 2>/dev/null || true
    kill -KILL 0 2>/dev/null || true
}
trap '_handle_signal' INT TERM
trap 'cleanup_lock' EXIT

# All phase commits must land on a named feature branch so they're visible to
# `git branch` and to the post-Phase-3 merge step. Detached HEAD is detected
# via exit status (not a string sentinel) to handle a real branch literally
# named "detached".
if _CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null); then
    _BRANCH_REASON=""
    case "$_CURRENT_BRANCH" in
        master|main) _BRANCH_REASON="'$_CURRENT_BRANCH'" ;;
    esac
else
    _BRANCH_REASON="detached HEAD (commits would be unreachable from any branch)"
fi
if [ -n "$_BRANCH_REASON" ]; then
    echo "ERROR: phase2.sh must not run on $_BRANCH_REASON."
    echo "Create a feature branch first: git checkout -b feature/<name>"
    exit 1
fi

NEXT=$(python3 -c "
import re, os
done = set()
if os.path.exists('CompletedSteps.md'):
    with open('CompletedSteps.md') as f:
        for line in f:
            m = re.search(r'Step (\d+): DONE', line)
            if m:
                done.add(int(m.group(1)))
n = 1
while n in done:
    n += 1
print(n)
")

STEP_PAD=$(printf '%02d' "$NEXT")
STEP_FILE="plans/step${STEP_PAD}.md"
HALT_FILE="plans/halt-step${STEP_PAD}.md"

# --- ai-routing.csv helpers ---------------------------------------------------
ROUTING_LOG="logs/ai-routing.csv"
ROUTING_HEADER="date,repo,task_type,tier_used,model,escalated_from,tests_passed,diff_lines_approx,human_rework_minutes,outcome"
log_routing() {
    # log_routing <task_type> <tests_passed:true|false> <diff_lines_approx> <outcome>
    local task_type="$1"
    local tests_passed="$2"
    local diff_lines="$3"
    local outcome="$4"
    local repo_name date
    repo_name=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || echo .)")
    date=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    if [ -d "$(dirname "$ROUTING_LOG")" ]; then
        # Recreate header if the file is missing or empty so downstream tooling
        # always sees a parseable CSV.
        if [ ! -s "$ROUTING_LOG" ]; then
            echo "$ROUTING_HEADER" > "$ROUTING_LOG"
        fi
        echo "${date},${repo_name},${task_type},1,local,,${tests_passed},${diff_lines},,${outcome}" >> "$ROUTING_LOG"
    fi
}

if [ ! -f "$STEP_FILE" ]; then
    if [ "$NEXT" -eq 1 ]; then
        echo "No step files found. Run Phase 1 first to generate plans/step01.md"
        exit 0
    fi

    echo "All steps complete."

    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | sed 's|.*/||' || echo "plan")
    ARCHIVE="plans/$(date +%Y-%m)-${BRANCH}.md"

    if [ ! -f "$ARCHIVE" ]; then
        echo ""
        echo "The following actions will be taken:"
        echo "  - Remove per-step files: plans/step*.md"
        if [ -f "PLAN.md" ]; then
            echo "  - Archive PLAN.md to $ARCHIVE"
        fi
        echo ""
        if [ -t 0 ]; then
            read -r -p "Proceed with cleanup and archive? [Y/N] " CONFIRM
            case "$CONFIRM" in
                [Yy]*) ;;
                *)
                    echo "No action will be taken."
                    exit 0
                    ;;
            esac
        else
            echo "Non-interactive session — skipping cleanup. Re-run interactively to archive."
            exit 0
        fi

        echo "Removing per-step files from plans/"
        git rm -f plans/step*.md 2>/dev/null || true

        if [ -f "PLAN.md" ]; then
            echo "Archiving PLAN.md to $ARCHIVE"
            cp PLAN.md "$ARCHIVE"
            git add "$ARCHIVE"
        fi

        if ! git diff --cached --quiet; then
            git commit -m "Archive PLAN.md to $ARCHIVE; remove per-step files"
        fi
    else
        echo "Archive already exists at $ARCHIVE — skipping."
    fi

    exit 0
fi

echo "==> Step $NEXT: $STEP_FILE"

# Token-cap soft check. The Phase 1 spec caps step files at 400 tokens (~300
# words); warn at >320 words so drift surfaces before it bites Aider's 10K
# context window. Non-fatal — the run continues.
if command -v wc >/dev/null 2>&1; then
    WORDS=$(wc -w < "$STEP_FILE" | tr -d '[:space:]')
    if [ "${WORDS:-0}" -gt 320 ]; then
        echo "==> WARN: $STEP_FILE is ${WORDS} words (cap ~300 / 400 tokens). Consider splitting in PLAN.md." >&2
    fi
fi

LOG_FILE="plans/step${STEP_PAD}.log"
if [ -f "$LOG_FILE" ]; then
    LOG_N=2
    while [ -f "plans/step${STEP_PAD}-${LOG_N}.log" ]; do
        LOG_N=$((LOG_N + 1))
    done
    LOG_FILE="plans/step${STEP_PAD}-${LOG_N}.log"
fi

# Wall-clock cap (timeout 15m) limits the blast radius of a fundamentally
# underspecified step. Note: aider does not expose a --max-reflections flag
# in the version used here; the retry count is not configurable via CLI or
# config and defaults to aider's internal limit.
# `timeout(1)` is GNU coreutils — present on Linux, but not in stock macOS.
# Probe for existence first, then probe for --kill-after support (a GNU
# extension absent in busybox and BSD timeout). On macOS without coreutils
# the existence check fails and TIMEOUT_CMD is left empty. On busybox/Alpine
# the existence check passes but the capability check fails, falling back to
# plain timeout so the script doesn't break with an invalid-option error.
# Users who want --kill-after support can install GNU coreutils
# (`brew install coreutils` exposes `gtimeout`, or symlink it as `timeout`).
if command -v timeout >/dev/null 2>&1; then
    if timeout --kill-after=1s 1s true 2>/dev/null; then
        TIMEOUT_CMD=(timeout --kill-after=30s 15m)
    else
        echo "==> WARN: 'timeout' found but does not support --kill-after (busybox or BSD?); using plain timeout." >&2
        echo "    Install GNU coreutils for hard-kill support on stuck aider processes." >&2
        TIMEOUT_CMD=(timeout 15m)
    fi
else
    echo "==> WARN: 'timeout' not found; running aider without a wall-clock cap." >&2
    echo "    Install coreutils to enable the 15-minute step timeout." >&2
    TIMEOUT_CMD=()
fi

# ── Preflight: fail fast if the model endpoint / API key is unavailable ───────
# Derive model from env first, then from .aider.conf.yml so the check works
# whether the user sets AIDER_MODEL or relies on the config file.
# See NIMBUS_GUIDE.md "Aider config note" for the .aider.conf.yml subset
# this reader supports.
_read_aider_conf_scalar() {
    [ -f ".aider.conf.yml" ] || return 0
    grep -m1 "^$1:" .aider.conf.yml 2>/dev/null \
        | sed "s/^$1:[[:space:]]*//" \
        | tr -d '"'"'" || true
}

_PREFLIGHT_MODEL="${AIDER_MODEL:-}"
[ -z "$_PREFLIGHT_MODEL" ] && _PREFLIGHT_MODEL=$(_read_aider_conf_scalar model)

if [ -n "$_PREFLIGHT_MODEL" ]; then
    _PREFLIGHT_API_KEY="${OPENAI_API_KEY:-}"
    _PREFLIGHT_BASE_URL="${OPENAI_BASE_URL:-}"
    [ -z "$_PREFLIGHT_API_KEY" ]  && _PREFLIGHT_API_KEY=$(_read_aider_conf_scalar openai-api-key)
    [ -z "$_PREFLIGHT_BASE_URL" ] && _PREFLIGHT_BASE_URL=$(_read_aider_conf_scalar openai-api-base)

    case "$_PREFLIGHT_MODEL" in
        openai/*|gpt-*|o1*|o3*)
            # OpenAI-compatible model: needs an API key or a local base URL.
            if [ -z "$_PREFLIGHT_API_KEY" ] && [ -z "$_PREFLIGHT_BASE_URL" ]; then
                echo "==> ERROR: model '$_PREFLIGHT_MODEL' requires OPENAI_API_KEY or OPENAI_BASE_URL to be set (or openai-api-key / openai-api-base in .aider.conf.yml). Aborting."
                exit 1
            fi
            # If pointing at a local server, verify it is actually reachable before
            # handing control to aider (which would otherwise hang on retries).
            if [ -n "$_PREFLIGHT_BASE_URL" ] && command -v curl >/dev/null 2>&1; then
                _AUTH_HEADER=()
                [ -n "$_PREFLIGHT_API_KEY" ] && _AUTH_HEADER=(-H "Authorization: Bearer ${_PREFLIGHT_API_KEY}")
                if ! curl -sf --max-time 5 "${_PREFLIGHT_BASE_URL%/}/models" \
                     "${_AUTH_HEADER[@]}" -o /dev/null 2>/dev/null; then
                    echo "==> ERROR: local model server at '${_PREFLIGHT_BASE_URL}' is not reachable. Aborting."
                    exit 1
                fi
            fi
            ;;
        anthropic/*|claude-*)
            if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
                echo "==> ERROR: model '$_PREFLIGHT_MODEL' requires ANTHROPIC_API_KEY to be set. Aborting."
                exit 1
            fi
            ;;
    esac
fi

# Interrupted-run recovery: phase2.sh writes a sentinel to .git/ immediately
# before invoking Aider and removes it after a successful commit. If the
# sentinel already exists at startup, the previous run was interrupted
# mid-step (Ctrl+C, timeout, crash). In that case run verify.sh first; if it
# passes, skip Aider and go straight to record-and-commit.
#
# Storing the sentinel in .git/ means it is never committed, is unaffected by
# user edits to source files or config (no false positives), and survives any
# kill signal including SIGKILL.
WIP_FILE=".git/phase2-wip-step${STEP_PAD}"

# Pathspec excludes shared by the dirty-tree check and the post-aider commit:
# build-artifact dirs whose contents are not part of the step diff, plus the
# transient aider log.
_BUILD_EXCLUDES=(
    ':!target' ':!build' ':!.gradle'
    ':!node_modules' ':!dist' ':!out'
)
_COMMIT_EXCLUDES=("${_BUILD_EXCLUDES[@]}" ':!plans/*.log')

# Refuse to start with a dirty working tree unless a WIP sentinel signals an
# interrupted prior run for this step. Without this guard the bottom-of-script
# `git add -A` would silently sweep unrelated edits into the step commit.
if [ ! -f "$WIP_FILE" ]; then
    DIRTY=$(git status --porcelain -- '.' "${_BUILD_EXCLUDES[@]}" 2>/dev/null || true)
    if [ -n "$DIRTY" ]; then
        echo "ERROR: working tree has uncommitted changes (and no interrupted-run sentinel)."
        echo "       Commit, stash, or discard them before running phase2.sh — otherwise they"
        echo "       would be swept into the step commit by 'git add -A'."
        echo ""
        echo "Offending paths:"
        printf '%s\n' "$DIRTY" | sed 's/^/  /'
        exit 1
    fi
fi

SKIP_AIDER=false
if [ -f "$WIP_FILE" ]; then
    echo "==> Interrupted-run sentinel found for step $NEXT — running pre-flight verify..."
    PREFLIGHT_EXIT=0
    set +e
    # Same background-subshell pattern as the Aider invocation: `wait` is
    # immediately interruptible by signals whereas a foreground pipeline defers
    # trap execution until the pipeline finishes.
    (
      ./verify.sh 2>&1 | tee "$LOG_FILE"
      exit "${PIPESTATUS[0]}"
    ) &
    _PREFLIGHT_SUBSHELL=$!
    wait "$_PREFLIGHT_SUBSHELL"
    PREFLIGHT_EXIT=$?
    set -e
    if [ "$PREFLIGHT_EXIT" -eq 0 ]; then
        echo "==> Pre-flight verify passed — step $NEXT appears already complete. Skipping Aider."
        SKIP_AIDER=true
    else
        echo "==> Pre-flight verify failed — proceeding with Aider."
    fi
fi

# Parse a path entry from a "## Files to change" list item in a step file.
# Strips the leading "- " marker, any remaining leading whitespace (handles the
# double-space typo '- ⎵⎵src/...'), a trailing "(annotation)" suffix, and one
# layer of `/"/' wrapping. Called from both the FILE_ARGS setup below and the
# planned-file existence guard; defined here so both uses share the same parser
# regardless of the SKIP_AIDER path.
_strip_md_path() {
    local p="${1#- }"
    # Strip any leading whitespace left after removing the "- " prefix.
    # Without this, '- ⎵⎵src/Foo.java' (double space) leaves ' src/Foo.java'
    # which the embedded-space guard would silently skip rather than check.
    p="${p#"${p%%[![:space:]]*}"}"
    # Strip trailing annotation: shortest-match " (*" removes only the trailing
    # " (note)" suffix. Using % not %% avoids truncating at the first ( in a
    # directory component (e.g. com/example(v1)/Foo.java is left intact).
    p="${p% (*}"
    p="${p%"${p##*[![:space:]]}"}"
    p="${p#\`}"; p="${p%\`}"
    p="${p#\"}"; p="${p%\"}"
    p="${p#\'}"; p="${p%\'}"
    printf '%s' "$p"
}

if [ "$SKIP_AIDER" = false ]; then
    # Pass each existing planned path as --file so Aider sees real content
    # instead of hallucinating SEARCH blocks. Paths with embedded spaces are
    # skipped — bash word-splitting would complicate the --file plumbing and
    # real paths in these projects never contain spaces.
    FILE_ARGS=()
    PARSED_COUNT=0
    while IFS= read -r f; do
        path=$(_strip_md_path "$f")
        [ -z "$path" ] && continue
        case "$path" in
            *" "*)
                echo "==> WARN: skipping path with embedded space: $path" >&2
                continue
                ;;
        esac
        PARSED_COUNT=$((PARSED_COUNT + 1))
        if [ -f "$path" ]; then
            FILE_ARGS+=("--file" "$path")
        fi
    done < <(awk '/^## Files to change/{found=1; next} found && /^##/{exit} found && /^- /{print}' "$STEP_FILE")

    if [ "$PARSED_COUNT" -eq 0 ]; then
        echo "==> WARN: no entries parsed from '## Files to change' in $STEP_FILE." >&2
        echo "    Aider will run without explicit --file args and may hallucinate SEARCH blocks." >&2
    elif [ "${#FILE_ARGS[@]}" -eq 0 ]; then
        echo "==> WARN: '## Files to change' lists $PARSED_COUNT path(s) but none exist on disk yet." >&2
        echo "    Aider will create them from scratch; if existing files were intended, check the step file." >&2
    fi

    touch "$WIP_FILE"
    AIDER_EXIT=0
    set +e
    # Run the pipeline in a background subshell so that `wait` is used instead of
    # a foreground pipeline. Bash defers trap execution until foreground commands
    # finish, meaning Ctrl+C can't fire _handle_signal while aider is blocking.
    # `wait <pid>` is immediately interruptible — the trap runs the moment the
    # signal arrives. The subshell propagates aider's exit code (including 124 for
    # timeout) via `exit "${PIPESTATUS[0]}"`.
    # ${arr[@]+"${arr[@]}"} avoids tripping `set -u` on empty arrays under bash < 4.4.
    (
      ${TIMEOUT_CMD[@]+"${TIMEOUT_CMD[@]}"} aider \
        --no-auto-commits \
        --no-show-model-warnings \
        --map-tokens 0 \
        --no-suggest-shell-commands \
        --read "$STEP_FILE" \
        --read CONTEXT.md \
        ${FILE_ARGS[@]+"${FILE_ARGS[@]}"} \
        --no-auto-test \
        --yes \
        -m "Implement only the step in $STEP_FILE. CONTEXT.md has invariants and do-not-change areas. Do not run tests; the shell verifies after you exit." \
        2>&1 | tee -a "$LOG_FILE"
      _ps=("${PIPESTATUS[@]}")
      _aider_rc="${_ps[0]}"
      _tee_rc="${_ps[1]:-0}"
      if [ "$_tee_rc" -ne 0 ]; then
        echo "==> WARN: tee failed writing $LOG_FILE (exit ${_tee_rc} — disk full?)" >&2
      fi
      exit "$_aider_rc"
    ) &
    _AIDER_SUBSHELL=$!
    wait "$_AIDER_SUBSHELL"
    AIDER_EXIT=$?
    set -e

    # 124 = SIGTERM from timeout; 137 = SIGKILL from --kill-after (128 + 9).
    if { [ "$AIDER_EXIT" -eq 124 ] || [ "$AIDER_EXIT" -eq 137 ]; } && [ "${#TIMEOUT_CMD[@]}" -gt 0 ]; then
        echo "==> Aider hit the 15-minute timeout — step $NEXT NOT recorded. Inspect $LOG_FILE."
        exit 1
    fi

    if [ "$AIDER_EXIT" -ne 0 ]; then
        echo "==> Aider exited $AIDER_EXIT — step $NEXT NOT recorded."
        exit "$AIDER_EXIT"
    fi

    # Token-limit guard: some local models emit a "token limit" message and still
    # exit 0, but produce a truncated or malformed response (e.g. hundreds of
    # repeated imports that fill the context, then nothing). Treat any such log
    # entry as a hard failure so the step is not recorded as done.
    if [ -f "$LOG_FILE" ] && grep -qiE "(has hit a token limit|token limit exceeded|context\.length exceeded|maximum context length|input is too long|KV cache is full|Prompt is too long|Prompt exceeds context|context overflow|n_predict tokens limit)" "$LOG_FILE" 2>/dev/null; then
        echo "==> Model hit a token limit — output may be truncated or malformed. Step $NEXT NOT recorded."
        echo "    Inspect $LOG_FILE. Consider splitting this step or reducing CONTEXT.md."
        rm -f "$WIP_FILE"
        exit 1
    fi

    # Repeated-output (degenerate generation) guard: local models can enter a loop
    # emitting the same token sequence — import lines, class names, etc. — until the
    # Tabby/litellm server aborts the completion. If litellm eventually gives up and
    # aider exits 0 (rather than timing out), the output is partial or garbage not
    # caught by the token-limit grep above (no "token limit" message in the abort
    # path). Detect it by counting the max occurrence of any non-trivial line in the
    # Aider output. Note: this guard only fires when AIDER_EXIT==0; the timeout case
    # (exit 124/137) is caught above and exits before reaching here.
    # Note: the pipeline exits 0 on an empty log (each stage succeeds with no output),
    # so _repeat_max will be empty rather than "0" — the :-0 default handles that.
    if [ -f "$LOG_FILE" ]; then
        _repeat_max=$(awk 'length > 10' "$LOG_FILE" 2>/dev/null \
            | sort | uniq -c | sort -rn \
            | awk 'NR==1{print $1; exit}')
        if [ "${_repeat_max:-0}" -gt 30 ]; then
            echo "==> Degenerate model output detected (a line repeated ${_repeat_max}× in log) — step $NEXT NOT recorded."
            echo "    The local model likely looped generating the same tokens until litellm aborted."
            echo "    Inspect $LOG_FILE. Consider splitting this step or using a stronger model."
            rm -f "$WIP_FILE"
            exit 1
        fi
    fi

    # Aider-health warning: Aider can apply edits and still fail at its internal
    # context summarization ("Summarization failed") or crash with an unhandled
    # exception. These are internal failures, not proof that edits are wrong —
    # verify.sh is the deterministic gate. Log a visible warning here so the step
    # log captures the signal; if verify.sh also fails, the combined log gives
    # full context for root-cause analysis.
    if [ -f "$LOG_FILE" ] && grep -qiE "(Summarization failed|summarizer unexpectedly failed|Traceback \(most recent call last\)|unhandled exception)" "$LOG_FILE" 2>/dev/null; then
        echo "==> WARN: Aider internal failure detected (summarization error or exception) — see $LOG_FILE." >&2
        echo "    Proceeding to verify.sh; if it fails, Aider may have produced partial output." >&2
    fi

    # Halt detection: if the executor produced or modified plans/halt-stepNN.md
    # during this run, it intentionally stopped because a required prior artifact
    # was missing. Treat the halt file's dirty status as authoritative — partial
    # edits in other files MUST NOT be committed as DONE. We commit only the halt
    # report (so it survives across retries) and discard any other in-tree changes.
    # Exit 2 so the caller can distinguish a halt from a verify.sh failure.
    #
    # `git status --porcelain -- <path>` returns a non-empty line iff the path is
    # untracked, modified, or staged. A halt file committed in a previous run
    # would be clean, so this check fires only for halts produced *this run*.
    if [ -n "$(git status --porcelain -- "$HALT_FILE" 2>/dev/null)" ]; then
        echo "==> Step $NEXT halted: $HALT_FILE was written by the executor."
        echo "    Discarding any unrelated in-tree changes from this run."
        echo "    Review the halt report, fix the upstream gap, then re-run ./phase2.sh."
        git reset -q HEAD -- . 2>/dev/null || true    # unstage everything
        git add -- "$HALT_FILE"                       # restage only the halt file
        git commit -m "Step $NEXT: HALT (missing prior artifact)"
        git checkout -- . 2>/dev/null || true         # discard tracked-file edits
        git clean -fd 2>/dev/null || true             # remove untracked, non-ignored files
        log_routing "step-${STEP_PAD}" "false" "0" "halted"
        rm -f "$WIP_FILE"
        exit 2
    fi

    # Guard against aider exiting 0 without touching anything (e.g. unreachable model, bad API key).
    # If no files changed, the model was never reached — do not mark the step done.
    if git diff --quiet && git diff --cached --quiet; then
        echo "==> Aider made no changes — model may not have been reached (check API key / endpoint). Step $NEXT NOT recorded."
        exit 1
    fi

fi

# Halt detection — recovery path: inside SKIP_AIDER=false the halt check fires
# if Aider wrote the halt file during this run (lines 473–494). But if that run
# was killed between halt-file creation and the halt commit, the WIP sentinel
# persists and the next invocation takes the SKIP_AIDER=true path, bypassing
# the inner block entirely. This outer check catches that case so the halt
# report is always committed and exit 2 is always returned on a halt.
# On the SKIP_AIDER=false path this check is unreachable: the inner halt block
# already exited 2 before we reach here.
if [ -n "$(git status --porcelain -- "$HALT_FILE" 2>/dev/null)" ]; then
    echo "==> Step $NEXT halted (recovery): $HALT_FILE was written by the prior run."
    echo "    Discarding any unrelated in-tree changes."
    echo "    Review the halt report, fix the upstream gap, then re-run ./phase2.sh."
    git reset -q HEAD -- . 2>/dev/null || true
    git add -- "$HALT_FILE"
    git commit -m "Step $NEXT: HALT (missing prior artifact)"
    git checkout -- . 2>/dev/null || true
    git clean -fd 2>/dev/null || true
    log_routing "step-${STEP_PAD}" "false" "0" "halted"
    rm -f "$WIP_FILE"
    exit 2
fi

# Malformed-path guard runs BEFORE the planned-file existence check so that
# garbage files Aider created at bad paths are cleaned up first. Without this
# ordering, a garbage-path artifact would cause the existence guard to fire
# and exit 1 before git clean runs, leaving the garbage file in the working
# tree and causing the next invocation's dirty-tree guard to block.
_MP=$(git status --porcelain -- '.' "${_BUILD_EXCLUDES[@]}" 2>/dev/null \
        | grep -E '\*\*' || true)
if [ -n "$_MP" ]; then
    echo "==> ERROR: files with malformed paths detected — likely model output artifact. Step $NEXT NOT recorded."
    echo "    Pattern '**' found in the following working-tree paths:"
    printf '%s\n' "$_MP" | sed 's/^/    /'
    echo "    Discarding malformed files and resetting working tree."
    git checkout -- . 2>/dev/null || true
    git clean -fd 2>/dev/null || true
    rm -f "$WIP_FILE"
    exit 1
fi

# Planned-file existence guard: every path listed in "## Files to change" must
# exist on disk. Placed outside the SKIP_AIDER block so recovery runs
# (SKIP_AIDER=true) are also protected. Uses [ -e ] to accept directories too.
_MISSING_PLANNED=()
while IFS= read -r _pf; do
    _ppath=$(_strip_md_path "$_pf")
    [ -z "$_ppath" ] && continue
    case "$_ppath" in *" "*) continue ;; esac
    [ -e "$_ppath" ] || _MISSING_PLANNED+=("$_ppath")
done < <(awk '/^## Files to change/{found=1; next} found && /^##/{exit} found && /^- /{print}' "$STEP_FILE")
if [ "${#_MISSING_PLANNED[@]}" -gt 0 ]; then
    echo "==> ERROR: planned file(s) missing — step $NEXT NOT recorded."
    printf '    missing: %s\n' "${_MISSING_PLANNED[@]}"
    if [ "$SKIP_AIDER" = true ]; then
        # Recovery path: the prior Aider run may have left partial changes.
        # Preserve WIP_FILE when the tree is dirty so the next invocation retries
        # the SKIP_AIDER=true path — if verify.sh then fails, SKIP_AIDER flips to
        # false and Aider re-runs to complete the step. When the tree is clean
        # (Aider was killed before writing anything), remove WIP_FILE so the next
        # invocation runs Aider fresh instead of looping through SKIP_AIDER=true.
        _RECOVERY_DIRTY=$(git status --porcelain -- '.' "${_BUILD_EXCLUDES[@]}" 2>/dev/null || true)
        if [ -n "$_RECOVERY_DIRTY" ]; then
            echo "    The prior Aider run left uncommitted partial changes in the working tree."
            echo "    Re-run ./phase2.sh — if verify.sh fails, Aider will be re-invoked to"
            echo "    complete the step. To discard partial changes and start fresh:"
            echo "      git checkout -- . && git clean -fd && rm -f '${WIP_FILE}'"
        else
            echo "    The prior Aider run appears to have made no changes. Re-running"
            echo "    ./phase2.sh will invoke Aider fresh to complete the step."
            rm -f "$WIP_FILE"
        fi
    else
        echo "    Aider may have skipped creating these paths. Inspect $LOG_FILE."
        echo "    Note: non-parenthesis annotations (em-dash, colon) on list entries are"
        echo "    not stripped and cause the entry to be silently skipped. Use '(note)' format."
        rm -f "$WIP_FILE"
    fi
    exit 1
fi

# Shell owns bookkeeping — runs after aider exits, independently of whether aider's
# internal summarization completed. Prevents lost progress on aider crashes post-verification.
# verify.sh output is appended to the step log so one file contains both Aider output
# and verification results, making root-cause analysis on failed steps much easier.
# Capture the full PIPESTATUS array atomically before any other command can reset it,
# then check tee separately — mirrors the same pattern used in the Aider subshell.
_verify_ps=()
set +e
./verify.sh 2>&1 | tee -a "$LOG_FILE"
_verify_ps=("${PIPESTATUS[@]}")
set -e
VERIFY_EXIT="${_verify_ps[0]}"
_verify_tee_rc="${_verify_ps[1]:-0}"
if [ "$_verify_tee_rc" -ne 0 ]; then
    echo "==> WARN: tee failed writing $LOG_FILE (exit ${_verify_tee_rc} — disk full?)" >&2
fi
if [ "$VERIFY_EXIT" -eq 0 ]; then
    [ -f CompletedSteps.md ] || echo "# Completed Steps" > CompletedSteps.md
    echo "Step $NEXT: DONE" >> CompletedSteps.md
    git add -A -- '.' "${_COMMIT_EXCLUDES[@]}"
    git commit -m "Step $NEXT: complete"
    rm -f "$WIP_FILE"
    DIFF_LINES=$(git show --numstat HEAD 2>/dev/null | awk '{a+=$1+$2} END {print a+0}')
    log_routing "step-${STEP_PAD}" "true" "${DIFF_LINES:-0}" "done"
    echo "==> Step $NEXT committed."
else
    echo "==> verify.sh failed after aider exited — step $NEXT NOT recorded."
    exit 1
fi
