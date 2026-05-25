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
# Probe and fall back to running aider unbounded with a clear warning rather
# than failing the run; users who want the wall-clock cap can install
# coreutils (`brew install coreutils` exposes `gtimeout`, or symlink it as
# `timeout`).
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT_CMD=(timeout 15m)
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
    DIRTY=$(git status --porcelain -- "${_BUILD_EXCLUDES[@]}" 2>/dev/null || true)
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
    _PREFLIGHT_SUBSHELL=""
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

if [ "$SKIP_AIDER" = false ]; then
    # Parse "## Files to change" and pass each existing path as --file so Aider
    # sees real content instead of hallucinating SEARCH blocks. Strips a single
    # trailing "(annotation)" and one layer of `/"/' wrapping. Paths with
    # embedded spaces are skipped (PHASE1_SPEC.md examples never use them and
    # bash word-splitting would complicate the --file plumbing).
    _strip_md_path() {
        local p="${1#- }"
        p="${p%%(*}"
        p="${p%"${p##*[![:space:]]}"}"
        p="${p#\`}"; p="${p%\`}"
        p="${p#\"}"; p="${p%\"}"
        p="${p#\'}"; p="${p%\'}"
        printf '%s' "$p"
    }

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
    _AIDER_SUBSHELL=""
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
      _aider_rc="${PIPESTATUS[0]}"
      _tee_rc="${PIPESTATUS[1]}"
      if [ "${_tee_rc:-0}" -ne 0 ]; then
        echo "==> WARN: tee failed writing $LOG_FILE (exit ${_tee_rc} — disk full?)" >&2
      fi
      exit "$_aider_rc"
    ) &
    _AIDER_SUBSHELL=$!
    wait "$_AIDER_SUBSHELL"
    AIDER_EXIT=$?
    set -e

    if [ "$AIDER_EXIT" -eq 124 ] && [ "${#TIMEOUT_CMD[@]}" -gt 0 ]; then
        echo "==> Aider hit the 15-minute timeout — step $NEXT NOT recorded. Inspect $LOG_FILE."
        exit 1
    fi

    if [ "$AIDER_EXIT" -ne 0 ]; then
        echo "==> Aider exited $AIDER_EXIT — step $NEXT NOT recorded."
        exit "$AIDER_EXIT"
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

# Shell owns bookkeeping — runs after aider exits, independently of whether aider's
# internal summarization completed. Prevents lost progress on aider crashes post-verification.
if ./verify.sh; then
    [ -f CompletedSteps.md ] || echo "# Completed Steps" > CompletedSteps.md
    echo "Step $NEXT: DONE" >> CompletedSteps.md
    git add -A -- "${_COMMIT_EXCLUDES[@]}"
    git commit -m "Step $NEXT: complete"
    rm -f "$WIP_FILE"
    DIFF_LINES=$(git show --numstat HEAD 2>/dev/null | awk '{a+=$1+$2} END {print a+0}')
    log_routing "step-${STEP_PAD}" "true" "${DIFF_LINES:-0}" "done"
    echo "==> Step $NEXT committed."
else
    echo "==> verify.sh failed after aider exited — step $NEXT NOT recorded."
    exit 1
fi
