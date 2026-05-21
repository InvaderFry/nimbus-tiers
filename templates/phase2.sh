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
        # Two recovery attempts racing for the same stale lock can collide on the
        # re-mkdir. Retry with a short backoff so the loser doesn't falsely abort.
        LOCK_REACQUIRED=false
        for _attempt in 1 2 3; do
            if mkdir "$LOCK_DIR" 2>/dev/null; then
                LOCK_REACQUIRED=true
                break
            fi
            sleep 1
        done
        if [ "$LOCK_REACQUIRED" = true ]; then
            printf '%s\n' "$$" > "$LOCK_PID_FILE"
            get_proc_start_time "$$" > "$LOCK_START_FILE" 2>/dev/null || true
        else
            echo "ERROR: phase2 lock could not be recovered. Remove $LOCK_DIR (and any orphan files inside) and retry."
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
trap cleanup_lock EXIT INT TERM

# Refuse to run on master/main or in detached HEAD — all phase commits must
# land on a named feature branch so they are visible to `git branch` and to
# the post-Phase-3 merge step.
_CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
if [[ "$_CURRENT_BRANCH" == "master" || "$_CURRENT_BRANCH" == "main" ]]; then
    echo "ERROR: phase2.sh must not run on '$_CURRENT_BRANCH'."
    echo "Create a feature branch first: git checkout -b feature/<name>"
    exit 1
fi
if [[ "$_CURRENT_BRANCH" == "detached" ]]; then
    echo "ERROR: phase2.sh must not run in detached HEAD state."
    echo "Commits made here would be unreachable from any branch."
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
#
# .aider.conf.yml parsing subset: this is a `grep | sed | tr` reader, not a
# YAML parser. It only recognizes top-level scalar lines of the form
#     key: value          or          key: "value"          or          key: 'value'
# with the key starting at column 0. Quoted multi-line values, anchors, flow
# style, comments on the same line, and indented entries are NOT supported.
# Aider itself parses the full YAML, so a value outside this subset will still
# work at runtime — only the preflight check will skip it.
_PREFLIGHT_MODEL="${AIDER_MODEL:-}"
if [ -z "$_PREFLIGHT_MODEL" ] && [ -f ".aider.conf.yml" ]; then
    _PREFLIGHT_MODEL=$(grep -m1 '^model:' .aider.conf.yml 2>/dev/null \
                       | sed "s/^model:[[:space:]]*//" | tr -d '"'"'" || true)
fi

if [ -n "$_PREFLIGHT_MODEL" ]; then
    # Read openai-api-key / openai-api-base from .aider.conf.yml as fallbacks
    # so the preflight check mirrors what aider itself sees at runtime.
    _PREFLIGHT_API_KEY="${OPENAI_API_KEY:-}"
    _PREFLIGHT_BASE_URL="${OPENAI_BASE_URL:-}"
    if [ -f ".aider.conf.yml" ]; then
        [ -z "$_PREFLIGHT_API_KEY" ] && _PREFLIGHT_API_KEY=$(grep -m1 '^openai-api-key:' .aider.conf.yml 2>/dev/null \
            | sed "s/^openai-api-key:[[:space:]]*//" | tr -d '"'"'" || true)
        [ -z "$_PREFLIGHT_BASE_URL" ] && _PREFLIGHT_BASE_URL=$(grep -m1 '^openai-api-base:' .aider.conf.yml 2>/dev/null \
            | sed "s/^openai-api-base:[[:space:]]*//" | tr -d '"'"'" || true)
    fi

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

# Refuse to start with a dirty working tree (unless a WIP sentinel signals an
# interrupted prior run for this exact step). The commit at the bottom uses
# `git add -A`, so any unrelated uncommitted edits would be swept into the
# step commit and silently violate the one-step-per-commit contract that
# Phase 3 review depends on. Build-artifact directories are excluded so a
# previous test invocation doesn't block the next run.
if [ ! -f "$WIP_FILE" ]; then
    DIRTY=$(git status --porcelain 2>/dev/null \
        | grep -Ev '^.. (target/|build/|\.gradle/|node_modules/|dist/|out/)' \
        || true)
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
    ./verify.sh 2>&1 | tee "$LOG_FILE"
    PREFLIGHT_EXIT="${PIPESTATUS[0]}"
    set -e
    if [ "$PREFLIGHT_EXIT" -eq 0 ]; then
        echo "==> Pre-flight verify passed — step $NEXT appears already complete. Skipping Aider."
        SKIP_AIDER=true
    else
        echo "==> Pre-flight verify failed — proceeding with Aider."
    fi
fi

if [ "$SKIP_AIDER" = false ]; then
    # Parse "## Files to change" from the step file and pass each existing file
    # as --file so Aider sees the real content instead of hallucinating SEARCH blocks.
    # Accept formats produced by PHASE1_SPEC.md examples:
    #   - path/to/file
    #   - path/to/file (create if missing)
    #   - `path/to/file`
    #   - "path/to/file"
    # The parenthetical annotation is dropped; one layer of wrapping backticks
    # or quotes is stripped. Paths with embedded spaces are not supported (the
    # spec examples never use them and bash word-splitting would complicate the
    # --file plumbing); such paths are skipped with a warning.
    FILE_ARGS=()
    PARSED_PATHS=()
    while IFS= read -r f; do
        path="${f#- }"                              # strip leading "- "
        path="${path%%(*}"                           # drop trailing parenthetical annotation
        # trim trailing whitespace
        path="${path%"${path##*[![:space:]]}"}"
        # strip one layer of wrapping backticks / quotes
        path="${path#\`}"; path="${path%\`}"
        path="${path#\"}"; path="${path%\"}"
        path="${path#\'}"; path="${path%\'}"
        [ -z "$path" ] && continue
        case "$path" in
            *" "*)
                echo "==> WARN: skipping path with embedded space: $path" >&2
                continue
                ;;
        esac
        PARSED_PATHS+=("$path")
        if [ -f "$path" ]; then
            FILE_ARGS+=("--file" "$path")
        fi
    done < <(awk '/^## Files to change/{found=1; next} found && /^##/{exit} found && /^- /{print}' "$STEP_FILE")

    if [ "${#PARSED_PATHS[@]}" -eq 0 ]; then
        echo "==> WARN: no entries parsed from '## Files to change' in $STEP_FILE." >&2
        echo "    Aider will run without explicit --file args and may hallucinate SEARCH blocks." >&2
    elif [ "${#FILE_ARGS[@]}" -eq 0 ]; then
        echo "==> WARN: '## Files to change' lists ${#PARSED_PATHS[@]} path(s) but none exist on disk yet." >&2
        echo "    Aider will create them from scratch; if existing files were intended, check the step file." >&2
    fi

    touch "$WIP_FILE"
    AIDER_EXIT=0
    set +e
    # ${arr[@]+"${arr[@]}"} expands to nothing when the array is empty without
    # tripping `set -u` on bash < 4.4 (still default on macOS).
    "${TIMEOUT_CMD[@]+"${TIMEOUT_CMD[@]}"}" aider \
      --no-auto-commits \
      --no-show-model-warnings \
      --read "$STEP_FILE" \
      --read CONTEXT.md \
      ${FILE_ARGS[@]+"${FILE_ARGS[@]}"} \
      --test-cmd "./verify.sh" \
      --auto-test \
      --yes \
      -m "Implement only the step in $STEP_FILE. CONTEXT.md has invariants and do-not-change areas. Run ./verify.sh; if it fails, fix and retry." \
      2>&1 | tee -a "$LOG_FILE"
    AIDER_EXIT="${PIPESTATUS[0]}"
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
    git add -A -- ':!plans/*.log'
    git commit -m "Step $NEXT: complete"
    rm -f "$WIP_FILE"
    DIFF_LINES=$(git show --numstat HEAD 2>/dev/null | awk '{a+=$1+$2} END {print a+0}')
    log_routing "step-${STEP_PAD}" "true" "${DIFF_LINES:-0}" "done"
    echo "==> Step $NEXT committed."
else
    echo "==> verify.sh failed after aider exited — step $NEXT NOT recorded."
    exit 1
fi
