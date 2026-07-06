#!/usr/bin/env bash
# Phase 2 executor — runs one Aider step at a time against the local model.
# Re-run until all steps are complete; picks up where it left off via CompletedSteps.md.
# Usage: ./phase2.sh [--status | --dry-run | --help]
#
# Exit codes:
#   0  step recorded DONE (or all steps complete; archive performed)
#   1  Aider failure, empty diff, or verify.sh failed — step not recorded
#   2  step halted intentionally (plans/halt-stepNN.md written) — review halt report
#  64  unknown command-line argument
# With --status/--dry-run: 0 = a run could proceed, 1 = something blocks it.
set -euo pipefail

# Pure helpers (path parsing, guard regexes, log classifiers) live in
# phase2-lib.sh so they can be unit-tested in isolation. Both files are
# scaffolded together by nimbus-tiers and must stay side by side.
_PHASE2_DIR=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [ ! -f "${_PHASE2_DIR}/phase2-lib.sh" ]; then
    echo "ERROR: phase2-lib.sh not found next to phase2.sh (looked in ${_PHASE2_DIR})." >&2
    echo "       The two files ship together — restore it from the nimbus-tiers template or git history." >&2
    exit 1
fi
# shellcheck source=phase2-lib.sh
. "${_PHASE2_DIR}/phase2-lib.sh"

_usage() {
    cat <<'USAGE'
Usage: ./phase2.sh [--status | --dry-run | --help]

  (no flag)   Run the next step: invoke Aider, verify, commit.
  --status    Read-only pipeline report: next step, lock / WIP-sentinel /
              fail-marker state, dirty tree, verify.sh gate lint.
              Exit 0 if a run could proceed, 1 if something would block it.
              Never takes the lock and never writes.
  --dry-run   Run every pre-Aider check (branch guard, dirty-tree guard,
              gate lint, endpoint preflight, planned-path parse and the
              edit-format decision) without invoking Aider and without
              touching the working tree, .git/ bookkeeping, or step logs.
  --help      Show this help.
USAGE
}

NIMBUS_MODE=run
case "${1:-}" in
    '') ;;
    --status)  NIMBUS_MODE=status ;;
    --dry-run) NIMBUS_MODE=dryrun ;;
    --help|-h) _usage; exit 0 ;;
    *)
        echo "ERROR: unknown argument: $1" >&2
        _usage >&2
        exit 64
        ;;
esac

# Single-run guard: prevent concurrent phase2.sh executions in the same repo.
# A second run can race bookkeeping and produce confusing sentinel recovery.
# Acquisition is wrapped in a function so the read-only modes (--status,
# --dry-run) can skip it — they must not block on, steal, or clean up a live
# run's lock.
LOCK_DIR=".git/phase2.lock"
LOCK_PID_FILE="${LOCK_DIR}/pid"
LOCK_START_FILE="${LOCK_DIR}/starttime"
_acquire_lock() {
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
}
cleanup_lock() {
    rm -f "$LOCK_PID_FILE" 2>/dev/null || true
    rm -f "$LOCK_START_FILE" 2>/dev/null || true
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
_AIDER_SUBSHELL=""
_PREFLIGHT_SUBSHELL=""
_WATCHDOG_SUBSHELL=""
# Initialized before the traps are armed so _cleanup_empty_placeholders (called
# from _handle_signal) is safe even if a signal lands before the FILE_ARGS loop
# populates it. The loop re-initializes it to () in the SKIP_AIDER=false path.
_PLACEHOLDERS=()

# Remove placeholders we created for missing planned files that are still empty.
# Aider populates a placeholder only when it produces a valid edit, so on every
# failure path (watchdog kill, timeout, nonzero exit, token-limit/degenerate
# aborts) the stub is left 0-byte. Leaving it behind would either block the next
# run's dirty-tree guard (paths that clear the WIP sentinel) or let a 0-byte stub
# masquerade as a created file in the existence guard (paths that keep it). Call
# this before every failure exit after placeholders are created. Populated
# placeholders are intentionally kept so the success path can commit them. The
# ${arr[@]+...} guard is `set -u`-safe even before _PLACEHOLDERS is defined.
_cleanup_empty_placeholders() {
    local _ph
    for _ph in ${_PLACEHOLDERS[@]+"${_PLACEHOLDERS[@]}"}; do
        if [ -f "$_ph" ] && [ ! -s "$_ph" ]; then
            rm -f "$_ph"
        fi
    done
}

_handle_signal() {
    cleanup_lock
    # Remove empty placeholders before the group is killed. Without this an
    # interrupt after placeholder creation leaves 0-byte stubs behind; the WIP
    # sentinel persists, so the next run treats them as pre-existing files (not
    # placeholders), bypassing the empty-stub cleanup and existence guard.
    _cleanup_empty_placeholders
    # kill -KILL on the subshell process only; children (aider, tee, verify.sh)
    # inside it are NOT forwarded the signal — they survive until kill -KILL 0
    # kills the entire process group on the next line.
    # Running pipelines via background subshells + `wait` makes this trap fire
    # immediately on Ctrl+C instead of being deferred until the pipeline exits.
    [ -n "${_PREFLIGHT_SUBSHELL:-}" ] && kill -KILL "$_PREFLIGHT_SUBSHELL" 2>/dev/null || true
    [ -n "${_AIDER_SUBSHELL:-}" ] && kill -KILL "$_AIDER_SUBSHELL" 2>/dev/null || true
    [ -n "${_WATCHDOG_SUBSHELL:-}" ] && kill -KILL "$_WATCHDOG_SUBSHELL" 2>/dev/null || true
    kill -KILL 0 2>/dev/null || true
}
# Pathspec excludes shared by the dirty-tree checks, the post-aider commit,
# and --status: build-artifact dirs whose contents are not part of the step
# diff, plus the transient aider log. Defined before the mode dispatch so
# --status reports with exactly the pathspec a real run would use.
_BUILD_EXCLUDES=(
    ':!target' ':!build' ':!.gradle'
    ':!node_modules' ':!dist' ':!out'
)
_COMMIT_EXCLUDES=("${_BUILD_EXCLUDES[@]}" ':!plans/*.log')

# Excludes for the "Aider made no changes" guard ONLY. A change to .gitignore
# alone is housekeeping, not progress on the step — Aider rewrites .gitignore on
# startup (adding its own working-file globs), and any other tool may touch it
# too. If that is the *only* dirty path, the model did no real work and the step
# must NOT be allowed to reach verify.sh and be recorded DONE. The template
# .gitignore already pre-lists `.aider*` so Aider has no reason to edit it, but
# this guard is the backstop for any housekeeping-only change. Note: .gitignore
# is deliberately NOT in _COMMIT_EXCLUDES, so a step that legitimately edits it
# alongside real source changes still commits the .gitignore edit.
_NOCHANGE_EXCLUDES=("${_COMMIT_EXCLUDES[@]}" ':!.gitignore')

# Read-only pipeline report (--status). Reuses the same lib helpers and
# pathspecs as a real run so its verdicts cannot drift from the guards'.
# Returns 0 when a run could proceed, 1 when something would block it.
_phase2_status() {
    local _blocked=0 _b _next _pad _step_file _words _lp _dirty _done
    if _b=$(git symbolic-ref --short HEAD 2>/dev/null); then
        case "$_b" in
            master|main)
                echo "[--] branch: $_b — phase2.sh refuses to run here (checkout a feature branch)"
                _blocked=1
                ;;
            *) echo "[OK] branch: $_b" ;;
        esac
    else
        echo "[--] branch: detached HEAD — commits would be unreachable"
        _blocked=1
    fi

    _next=$(nimbus_next_step)
    _pad=$(printf '%02d' "$_next")
    _step_file="plans/step${_pad}.md"
    if [ -f "$_step_file" ]; then
        _words=$(wc -w < "$_step_file" | tr -d '[:space:]')
        if [ "${_words:-0}" -gt 320 ]; then
            echo "[~~] next step: $_next ($_step_file, ${_words} words — over the ~300-word cap; consider splitting)"
        else
            echo "[OK] next step: $_next ($_step_file, ${_words} words)"
        fi
    elif [ "$_next" -eq 1 ]; then
        echo "[--] next step: plans/step01.md missing — run Phase 1 first"
        _blocked=1
    else
        echo "[OK] next step: all steps complete (a run would offer to archive PLAN.md)"
    fi

    if [ -d "$LOCK_DIR" ]; then
        _lp=$(tr -cd '0-9' < "$LOCK_PID_FILE" 2>/dev/null || true)
        if [ -n "$_lp" ] && kill -0 "$_lp" 2>/dev/null; then
            echo "[--] lock: held by live PID $_lp — another run is active"
            _blocked=1
        else
            echo "[~~] lock: stale (owner PID ${_lp:-unknown} gone) — a run would auto-recover it"
        fi
    else
        echo "[OK] lock: free"
    fi

    if [ -f ".git/phase2-wip-step${_pad}" ]; then
        echo "[~~] wip sentinel: armed for step $_next — a run would try verify-first recovery"
    else
        echo "[OK] wip sentinel: none"
    fi

    if [ -f ".git/phase2-fail-step${_pad}" ]; then
        if [ -n "${PHASE2_FALLBACK_MODEL:-}" ]; then
            echo "[~~] fail marker: step $_next failed before — next run escalates to ${PHASE2_FALLBACK_MODEL}"
        else
            echo "[~~] fail marker: step $_next failed before (set PHASE2_FALLBACK_MODEL to auto-escalate)"
        fi
    else
        echo "[OK] fail marker: none"
    fi

    _dirty=$(git status --porcelain -- '.' "${_COMMIT_EXCLUDES[@]}" 2>/dev/null || true)
    if [ -n "$_dirty" ] && [ ! -f ".git/phase2-wip-step${_pad}" ]; then
        echo "[--] working tree: dirty — blocks a run (commit, stash, or discard first):"
        printf '%s\n' "$_dirty" | sed 's/^/       /'
        _blocked=1
    elif [ -n "$_dirty" ]; then
        echo "[~~] working tree: dirty — allowed for recovery (WIP sentinel armed)"
    else
        echo "[OK] working tree: clean"
    fi

    if [ -f verify.sh ]; then
        if nimbus_gate_swallows_exit verify.sh; then
            echo "[--] verify.sh: contains the 'if ! wait' exit-swallowing pattern — blocks a run (see PHASE1_VERIFY_HELPER.md)"
            _blocked=1
        else
            echo "[OK] verify.sh: present, gate lint clean"
        fi
    else
        echo "[~~] verify.sh: missing — a run would fail at the verify stage"
    fi

    if [ -f CompletedSteps.md ]; then
        _done=$(grep -c ': DONE' CompletedSteps.md 2>/dev/null || true)
        echo "     completed: ${_done:-0} step(s) recorded in CompletedSteps.md"
    fi
    return "$_blocked"
}

if [ "$NIMBUS_MODE" = status ]; then
    if _phase2_status; then exit 0; else exit 1; fi
fi

# The lock and its cleanup traps belong to real runs only: --dry-run mutates
# nothing (no bookkeeping to race) and arming the EXIT trap in a read-only
# mode would delete a live run's lock files on exit.
if [ "$NIMBUS_MODE" = run ]; then
    _acquire_lock
    trap '_handle_signal' INT TERM
    trap 'cleanup_lock' EXIT
fi

# Recursively SIGKILL a process and all of its descendants. Used by the
# degenerate-output watchdog to tear down just the aider pipeline (timeout,
# aider, tee) — unlike the signal handler's `kill -KILL 0`, which kills the
# whole process group and would also take down the watchdog and main script.
# Relies on `pgrep -P`; the watchdog is only enabled when that is available.
_kill_tree() {
    local pid="$1" child
    for child in $(pgrep -P "$pid" 2>/dev/null || true); do
        _kill_tree "$child"
    done
    kill -KILL "$pid" 2>/dev/null || true
}

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

NEXT=$(nimbus_next_step)

STEP_PAD=$(printf '%02d' "$NEXT")
STEP_FILE="plans/step${STEP_PAD}.md"
HALT_FILE="plans/halt-step${STEP_PAD}.md"
# Failure marker for the optional automatic fallback (PHASE2_FALLBACK_MODEL):
# written on model-failure exits, consumed at startup of the next run for the
# same step, removed on success and on intentional halts. Lives in .git/ for
# the same reasons as the WIP sentinel.
FAIL_MARKER=".git/phase2-fail-step${STEP_PAD}"

# --- ai-routing.csv helpers ---------------------------------------------------
ROUTING_LOG="logs/ai-routing.csv"
ROUTING_HEADER="date,repo,task_type,tier_used,model,escalated_from,tests_passed,diff_lines_approx,human_rework_minutes,outcome"
# Routing metadata defaults; overridden by the fallback activation block below.
_ROUTE_TIER=1
_ROUTE_MODEL=local
_ROUTE_ESCALATED_FROM=""
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
        echo "${date},${repo_name},${task_type},${_ROUTE_TIER},${_ROUTE_MODEL},${_ROUTE_ESCALATED_FROM},${tests_passed},${diff_lines},,${outcome}" >> "$ROUTING_LOG"
    fi
}

if [ ! -f "$STEP_FILE" ]; then
    if [ "$NEXT" -eq 1 ]; then
        echo "No step files found. Run Phase 1 first to generate plans/step01.md"
        exit 0
    fi

    echo "All steps complete."

    if [ "$NIMBUS_MODE" = dryrun ]; then
        echo "==> DRY RUN: a real run would offer to archive PLAN.md and remove plans/step*.md."
        exit 0
    fi

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

# In dry-run mode logf/logf_err still print to the terminal, but their log
# mirror goes to /dev/null — a dry run must not create or grow step logs.
if [ "$NIMBUS_MODE" = dryrun ]; then
    LOG_FILE=/dev/null
else
    LOG_FILE="plans/step${STEP_PAD}.log"
    if [ -f "$LOG_FILE" ]; then
        LOG_N=2
        while [ -f "plans/step${STEP_PAD}-${LOG_N}.log" ]; do
            LOG_N=$((LOG_N + 1))
        done
        LOG_FILE="plans/step${STEP_PAD}-${LOG_N}.log"
    fi
fi

# Step-log diagnostics. Aider and verify.sh output is teed into $LOG_FILE by
# their pipelines, but the script's own "==> ..." messages (timeouts,
# degenerate-output aborts, missing-file errors, verify failures) previously
# went only to the terminal — so a saved step log could not explain why a step
# failed. logf/logf_err mirror those messages into $LOG_FILE too. Each argument
# is printed on its own line. The append is best-effort: failures (e.g. a
# read-only dir) are swallowed so logging never aborts the run under `set -e`.
logf() {
    printf '%s\n' "$@"
    printf '%s\n' "$@" >> "$LOG_FILE" 2>/dev/null || true
}
logf_err() {
    printf '%s\n' "$@" >&2
    printf '%s\n' "$@" >> "$LOG_FILE" 2>/dev/null || true
}

# Record that this step failed at the model (not by intentional halt), so the
# next run can auto-escalate when PHASE2_FALLBACK_MODEL is set. Best-effort.
_mark_step_failed() {
    : > "$FAIL_MARKER" 2>/dev/null || true
}

# Required-.gitignore-entries repair: Aider can corrupt .gitignore when a step
# lists it as an edit target (observed: truncated to a single partial line).
# Losing `plans/*.log` is self-blocking — phase2.sh's own step logs become
# untracked files that trip the dirty-tree guard on later runs; losing `.aider*`
# invites Aider's startup rewrite to dirty the tree on every run. Re-append what
# is missing so one bad edit cannot wedge the pipeline; the repaired file is
# committed with the step, so Phase 3 review still sees the diff. The missing-
# entry computation (whole-line literal matching, ordered glob+negations block)
# lives in phase2-lib.sh: nimbus_missing_gitignore_entries. Idempotent
# (a repaired file needs nothing on the next call), so it is safe to invoke
# from both the post-Aider and the recovery paths.
_repair_gitignore() {
    local _append=() _gi
    while IFS= read -r _gi; do
        [ -n "$_gi" ] && _append+=("$_gi")
    done < <(nimbus_missing_gitignore_entries)
    if [ "${#_append[@]}" -eq 0 ]; then
        return 0
    fi
    {
        printf '\n%s\n' "# Restored by phase2.sh: required entries were missing after the Aider run."
        printf '%s\n' "${_append[@]}"
    } >> .gitignore
    logf_err "==> WARN: .gitignore was missing required entries after the Aider run — restored:"
    for _gi in "${_append[@]}"; do
        logf_err "    $_gi"
    done
    logf_err "    If the rest of .gitignore looks corrupted, restore it from history:" \
             "      git checkout HEAD -- .gitignore   (then re-apply any intended edits)"
}

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

# ── Optional automatic fallback ───────────────────────────────────────────────
# When PHASE2_FALLBACK_MODEL is set (e.g. groq/llama-3.3-70b-versatile) and the
# previous run of THIS step failed at the model (fail marker present), this run
# re-invokes Aider with the fallback model instead of the local default. One
# local failure is required first — the fallback never preempts the local tier.
# The fallback run is logged to logs/ai-routing.csv as tier 2, escalated_from
# local. If the fallback run also fails, the marker is re-written and the next
# run retries the fallback again; see NIMBUS_GUIDE.md "When a step keeps
# failing" for when to stop and go back to Phase 1.
FALLBACK_ACTIVE=false
MODEL_OVERRIDE_ARGS=()
if [ -n "${PHASE2_FALLBACK_MODEL:-}" ] && [ -f "$FAIL_MARKER" ]; then
    FALLBACK_ACTIVE=true
    MODEL_OVERRIDE_ARGS=(--model "$PHASE2_FALLBACK_MODEL")
    _ROUTE_TIER=2
    _ROUTE_MODEL="$PHASE2_FALLBACK_MODEL"
    _ROUTE_ESCALATED_FROM=local
    logf "==> Step ${NEXT} previously failed locally — retrying with fallback model ${PHASE2_FALLBACK_MODEL} (PHASE2_FALLBACK_MODEL)."
fi

# ── Preflight: fail fast if the model endpoint / API key is unavailable ───────
# Derive model from env first, then from .aider.conf.yml so the check works
# whether the user sets AIDER_MODEL or relies on the config file.
# _read_aider_conf_scalar (phase2-lib.sh) supports the flat YAML subset the
# template config uses — see NIMBUS_GUIDE.md "Aider config note".
_PREFLIGHT_MODEL="${AIDER_MODEL:-}"
[ -z "$_PREFLIGHT_MODEL" ] && _PREFLIGHT_MODEL=$(_read_aider_conf_scalar model)
# A fallback run talks to the fallback provider, not the local server — point
# the preflight at the model actually used this run.
[ "$FALLBACK_ACTIVE" = true ] && _PREFLIGHT_MODEL="$PHASE2_FALLBACK_MODEL"

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
            # Capture the /models body (not -o /dev/null) so we can also reconcile
            # the SERVED model against the configured one below.
            if [ -n "$_PREFLIGHT_BASE_URL" ] && command -v curl >/dev/null 2>&1; then
                _AUTH_HEADER=()
                [ -n "$_PREFLIGHT_API_KEY" ] && _AUTH_HEADER=(-H "Authorization: Bearer ${_PREFLIGHT_API_KEY}")
                # errexit/pipefail off for the reachability probe and the no-jq
                # parse below: a failed curl assignment or a no-match grep in the
                # pipeline would otherwise abort the whole script.
                set +e
                _MODELS_BODY=$(curl -sf --max-time 5 "${_PREFLIGHT_BASE_URL%/}/models" \
                     "${_AUTH_HEADER[@]}" 2>/dev/null)
                _CURL_RC=$?
                set -e
                if [ "$_CURL_RC" -ne 0 ]; then
                    echo "==> ERROR: local model server at '${_PREFLIGHT_BASE_URL}' is not reachable. Aborting."
                    exit 1
                fi
                # Reconcile configured label vs served model. Under TabbyAPI's
                # single-model mode the `model:` in .aider.conf.yml is a cosmetic
                # label, NOT a selector — the server serves whatever weights are
                # loaded. So aider's banner ("Model: <label>") can name a model that
                # is not the one actually running. That silent drift is exactly how a
                # quant/serving problem gets misattributed to the model choice.
                # Strip the provider prefix from the configured name, then check the
                # served /models payload for it. Report BOTH values and only warn
                # (non-fatal, no jq) — server id formatting (folder name vs label)
                # varies, so an equality gate would false-positive constantly.
                _CONFIGURED_BARE="${_PREFLIGHT_MODEL#openai/}"
                set +e
                _SERVED_IDS=$(printf '%s' "$_MODELS_BODY" \
                    | grep -oE '"id"[[:space:]]*:[[:space:]]*"[^"]+"' \
                    | sed -E 's/.*"id"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/' \
                    | paste -sd, -)
                printf '%s' "$_MODELS_BODY" | grep -qF "$_CONFIGURED_BARE"
                _SERVED_MATCH=$?
                set -e
                if [ -n "$_SERVED_IDS" ] && [ "$_SERVED_MATCH" -ne 0 ]; then
                    logf_err "==> WARN: configured model and served model differ." \
                        "    configured (.aider.conf.yml / AIDER_MODEL): ${_PREFLIGHT_MODEL}" \
                        "    served by ${_PREFLIGHT_BASE_URL%/} (/models): ${_SERVED_IDS}" \
                        "    Under TabbyAPI the 'model:' field is a label, not a selector — the" \
                        "    server runs whatever is loaded. Aider's banner will show the label," \
                        "    so it can misname the model that actually runs. If output quality is" \
                        "    poor (e.g. corrupted/verbatim-copy failures), check the inference" \
                        "    host's TabbyAPI config.yml (model_dir) and cache_mode (avoid 2/3-bit" \
                        "    KV cache; prefer 8,8 or FP16) before blaming the model choice." \
                        "    Set PHASE2_STRICT_MODEL_MATCH=1 to make this mismatch fatal."
                    # Opt-in hard gate. The default stays a warning because server id
                    # formatting (folder name vs label) varies and an equality gate
                    # would false-positive; but a mismatch that is real and ignored
                    # run after run is how weak/wrong-quant output gets misattributed
                    # to everything else first. Any non-empty value other than 0 arms it.
                    case "${PHASE2_STRICT_MODEL_MATCH:-}" in
                        ''|0) ;;
                        *)
                            logf_err "==> ERROR: aborting on model mismatch (PHASE2_STRICT_MODEL_MATCH is set)." \
                                "    Load the configured model on the inference host, or fix the 'model:'" \
                                "    label in .aider.conf.yml to match what the server actually serves."
                            exit 1
                            ;;
                    esac
                fi
                # Context-length floor. The single most common root cause of
                # degenerate repetition loops and phantom SEARCH/REPLACE blocks on
                # local models is a server-side max_seq_len too small for Aider's
                # prompt (system prompt + step file + CONTEXT.md + target files):
                # the prompt gets truncated mid-file and the model completes
                # garbage. TabbyAPI exposes the loaded model card at /model
                # (singular) with max_seq_len under `parameters`; other
                # OpenAI-compatible servers 404 there, in which case the check is
                # skipped. Set PHASE2_MIN_CTX=<n> to change the floor, or 0 to
                # disable the check entirely.
                _MIN_CTX="${PHASE2_MIN_CTX:-16384}"
                case "$_MIN_CTX" in
                    ''|*[!0-9]*)
                        logf_err "==> WARN: PHASE2_MIN_CTX='${_MIN_CTX}' is not a non-negative integer; using default 16384."
                        _MIN_CTX=16384
                        ;;
                esac
                if [ "$_MIN_CTX" -gt 0 ]; then
                    set +e
                    _MODEL_CARD=$(curl -sf --max-time 5 "${_PREFLIGHT_BASE_URL%/}/model" \
                        "${_AUTH_HEADER[@]}" 2>/dev/null)
                    _CARD_RC=$?
                    set -e
                    if [ "$_CARD_RC" -eq 0 ] && [ -n "$_MODEL_CARD" ]; then
                        set +e
                        _MAX_SEQ_LEN=$(printf '%s' "$_MODEL_CARD" | nimbus_max_seq_len)
                        set -e
                        if [ -n "$_MAX_SEQ_LEN" ]; then
                            logf "==> Served context length (max_seq_len): ${_MAX_SEQ_LEN}"
                            if [ "$_MAX_SEQ_LEN" -lt "$_MIN_CTX" ]; then
                                logf_err "==> ERROR: served max_seq_len (${_MAX_SEQ_LEN}) is below the required floor (${_MIN_CTX})." \
                                    "    A context window this small truncates Aider's prompt mid-file — the known" \
                                    "    root cause of degenerate repetition loops and SEARCH/REPLACE failures on" \
                                    "    local models. Fix the inference host's TabbyAPI config.yml: raise" \
                                    "    max_seq_len (16384–32768 for Qwen2.5-Coder-14B on a 16GB GPU) and use" \
                                    "    cache_mode Q8 or FP16 — see docs/tabbyapi-nimbus-example.yml in this repo." \
                                    "    Override the floor with PHASE2_MIN_CTX=<n>, or PHASE2_MIN_CTX=0 to skip" \
                                    "    this check. Aborting."
                                exit 1
                            fi
                        fi
                    else
                        logf "==> Note: server does not expose /v1/model (not TabbyAPI?) — skipping context-length check."
                    fi
                fi
            fi
            ;;
        anthropic/*|claude-*)
            if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
                echo "==> ERROR: model '$_PREFLIGHT_MODEL' requires ANTHROPIC_API_KEY to be set. Aborting."
                exit 1
            fi
            ;;
        groq/*)
            if [ -z "${GROQ_API_KEY:-}" ]; then
                echo "==> ERROR: model '$_PREFLIGHT_MODEL' requires GROQ_API_KEY to be set. Aborting."
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

# (_BUILD_EXCLUDES / _COMMIT_EXCLUDES / _NOCHANGE_EXCLUDES are defined above
# the mode dispatch so --status shares them.)

# Refuse to start with a dirty working tree unless a WIP sentinel signals an
# interrupted prior run for this step. Without this guard the bottom-of-script
# `git add -A` would silently sweep unrelated edits into the step commit.
# Uses _COMMIT_EXCLUDES (not _BUILD_EXCLUDES) so plans/*.log never counts as
# dirty: step logs are normally gitignored, but this script writes $LOG_FILE
# (preflight WARNs) BEFORE this check — so if .gitignore ever loses its
# plans/*.log rule (e.g. Aider corrupts the file), each run would otherwise
# create an untracked log and then block itself here, wedging the pipeline.
# The logs are also excluded from the step commit, so ignoring them is safe.
if [ ! -f "$WIP_FILE" ]; then
    DIRTY=$(git status --porcelain -- '.' "${_COMMIT_EXCLUDES[@]}" 2>/dev/null || true)
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

# Gate-integrity lint: refuse to trust a verify.sh containing the known
# exit-code-swallowing pattern `if ! wait "$pid"; then status=$?` — every
# build failure would report success and a broken step gets committed as DONE
# (observed: a pom.xml with non-resolving coordinates shipped as a "passing"
# step). This lints the one pattern that has actually shipped; verify.sh
# authorship rules live in PHASE1_SPEC §4. Detection semantics are documented
# with nimbus_gate_swallows_exit in phase2-lib.sh.
if [ -f verify.sh ] && nimbus_gate_swallows_exit verify.sh; then
    logf_err "==> ERROR: verify.sh contains an 'if ! wait ...' status check, which swallows the" \
             "    build's real exit code (inside that branch \$? is the status of the negated" \
             "    test — always 0). The gate is non-authoritative: failing builds would be" \
             "    recorded DONE. Fix verify.sh to capture the status directly, e.g.:" \
             "        wait \"\$pid\" || status=\$?" \
             "    (see PHASE1_VERIFY_HELPER.md), then re-run ./phase2.sh."
    exit 1
fi

# Stale-sentinel guard: a WIP sentinel with NO real uncommitted work is not a
# recoverable interruption — the prior run died (or bailed) before Aider
# produced anything. The recovery shortcut below would run verify.sh and, since
# a gate can pass trivially (PHASE1_SPEC requires exit 0 while the stack
# sentinel file is still absent), skip Aider and record the step DONE with zero
# real changes. Measured with _NOCHANGE_EXCLUDES so a housekeeping-only
# .gitignore edit does not count as recoverable work either. Clear the sentinel
# and fall through to a fresh Aider run instead.
if [ "$NIMBUS_MODE" = run ] && [ -f "$WIP_FILE" ] && [ -z "$(git status --porcelain -- '.' "${_NOCHANGE_EXCLUDES[@]}" 2>/dev/null)" ]; then
    echo "==> Interrupted-run sentinel found for step $NEXT but no uncommitted work to recover — clearing stale sentinel and running Aider fresh."
    rm -f "$WIP_FILE"
fi

# Dry-run reports sentinel state but never runs verify.sh (a build can dirty
# artifact dirs) and never clears the sentinel — it proceeds through the
# pre-Aider checks as a fresh run would.
if [ "$NIMBUS_MODE" = dryrun ] && [ -f "$WIP_FILE" ]; then
    echo "==> DRY RUN: WIP sentinel armed for step $NEXT — a real run would try verify-first recovery."
fi

SKIP_AIDER=false
if [ "$NIMBUS_MODE" = run ] && [ -f "$WIP_FILE" ]; then
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

# The malformed-JVM-path regex (_JVM_DOTTED_DIR_RE) and the "## Files to
# change" list parser (_strip_md_path, nimbus_planned_entries) live in
# phase2-lib.sh — shared by the pre-Aider planned-path check, the post-Aider
# working-tree guard, the existence guard, and the artifact scrubber, so all
# uses share one definition.

if [ "$SKIP_AIDER" = false ]; then
    # Pass each planned path as --file so Aider edits a real on-disk target
    # instead of hallucinating from-scratch SEARCH blocks (which local models
    # botch — the degenerate import-spam loop is the canonical failure). Existing
    # regular files are passed directly; missing files get an empty placeholder
    # created first so Aider still receives them as editable --file arguments.
    # Paths with embedded spaces are skipped — bash word-splitting would
    # complicate the --file plumbing and real paths here never contain spaces.
    FILE_ARGS=()
    PARSED_COUNT=0
    _MALFORMED_PLANNED=0
    _PLACEHOLDERS=()
    _EXISTING_TARGETS=()
    while IFS= read -r f; do
        path=$(_strip_md_path "$f")
        [ -z "$path" ] && continue
        case "$path" in
            *" "*)
                logf_err "==> WARN: skipping path with embedded space: $path"
                continue
                ;;
        esac
        # Reject paths that escape the repo: planned entries are always
        # repo-relative, so an absolute path or one with a '..' component is
        # malformed (or injected). Skipping it here avoids creating placeholder
        # files outside the working tree (mkdir -p / ': >' would otherwise write
        # them). The slash-wrapping matches '..' only as a whole path component,
        # so legitimate filenames like 'Foo..bar' are not rejected. The path is
        # left out of FILE_ARGS, so the existence guard later reports it missing
        # and the step is rejected cleanly with no out-of-repo side effects.
        case "$path" in
            /*)
                logf_err "==> WARN: skipping absolute planned path (must be repo-relative): $path"
                continue
                ;;
        esac
        case "/$path/" in
            *"/../"*)
                logf_err "==> WARN: skipping planned path that escapes the repo: $path"
                continue
                ;;
        esac
        # Reject a planned path whose directory component under a JVM source root
        # contains a `.` (e.g. src/main/java/com.example/Foo.java) — a
        # package-name-as-directory bug. Skipping it here is important: the
        # placeholder step below runs `mkdir -p "$(dirname "$path")"`, which would
        # otherwise CREATE the malformed directory from a bad plan. Left out of
        # FILE_ARGS, the path is reported by the existence guard and the step is
        # rejected cleanly. See PHASE1_SPEC §Java (package-to-directory mapping).
        # Count the rejection separately from PARSED_COUNT so the post-loop
        # messaging can say "malformed" rather than the misleading "no entries
        # parsed" when a malformed path is the only thing listed.
        if nimbus_is_malformed_jvm_path "$path"; then
            logf_err "==> WARN: skipping planned path with a dotted/parenthesised directory under a JVM source root (package-name-as-directory bug?): $path" \
                     "    A Java/Kotlin package maps to directories by replacing '.' with '/': com.example.app -> com/example/app."
            _MALFORMED_PLANNED=$((_MALFORMED_PLANNED + 1))
            continue
        fi
        PARSED_COUNT=$((PARSED_COUNT + 1))
        if [ -f "$path" ]; then
            FILE_ARGS+=("--file" "$path")
            _EXISTING_TARGETS+=("$path")
        elif [ -e "$path" ]; then
            # Exists but is not a regular file (e.g. a directory) — leave it for
            # the planned-file existence guard rather than placeholdering it.
            logf_err "==> WARN: planned path exists but is not a regular file (directory, symlink, special file?) — skipping as --file target: $path"
        elif [ -L "$path" ]; then
            # Dangling symlink: [ -e ] is false (link target is missing) but the
            # symlink itself is present. Do NOT fall through to placeholder
            # creation — ': > "$path"' would follow the link and write to
            # wherever it points (potentially outside the repo tree). Skip it.
            logf_err "==> WARN: planned path is a dangling symlink (target missing) — skipping as --file target: $path"
        else
            case "$path" in
                */) ;;  # directory-style entry — nothing to create as a file
                *)
                    if [ "$NIMBUS_MODE" = dryrun ]; then
                        # Classify only — a dry run must not create the
                        # placeholder file or its parent directories.
                        _PLACEHOLDERS+=("$path")
                        FILE_ARGS+=("--file" "$path")
                    elif mkdir -p "$(dirname "$path")" 2>/dev/null && : > "$path" 2>/dev/null; then
                        _PLACEHOLDERS+=("$path")
                        FILE_ARGS+=("--file" "$path")
                    else
                        logf_err "==> WARN: could not create placeholder for planned file: $path"
                    fi
                    ;;
            esac
        fi
    done < <(nimbus_planned_entries "$STEP_FILE")

    if [ "$PARSED_COUNT" -eq 0 ] && [ "$_MALFORMED_PLANNED" -gt 0 ]; then
        logf_err "==> WARN: every path in '## Files to change' in $STEP_FILE was rejected as a" \
                 "    malformed JVM source path (${_MALFORMED_PLANNED} path(s) — see per-path WARNs above)." \
                 "    Fix the package→directory layout in the step file (com.example.app -> com/example/app)." \
                 "    Aider will run without explicit --file args and may hallucinate SEARCH blocks."
    elif [ "$PARSED_COUNT" -eq 0 ]; then
        logf_err "==> WARN: no entries parsed from '## Files to change' in $STEP_FILE." \
                 "    Aider will run without explicit --file args and may hallucinate SEARCH blocks."
    elif [ "${#FILE_ARGS[@]}" -eq 0 ]; then
        logf_err "==> WARN: '## Files to change' lists $PARSED_COUNT path(s) but none could be added as --file targets" \
                 "    (non-regular files, dangling symlinks, placeholder failures, or directory-style entries — see per-path WARNs above)." \
                 "    Aider will run without explicit --file args and may hallucinate SEARCH blocks."
    elif [ "${#_PLACEHOLDERS[@]}" -gt 0 ]; then
        if [ "$NIMBUS_MODE" = dryrun ]; then
            logf "==> DRY RUN: would create ${#_PLACEHOLDERS[@]} empty placeholder(s) for missing planned file(s):"
        else
            logf "==> Created ${#_PLACEHOLDERS[@]} empty placeholder(s) for missing planned file(s) so Aider edits real targets:"
        fi
        for _ph in "${_PLACEHOLDERS[@]}"; do
            logf "    placeholder: $_ph"
        done
    fi

    # Select --edit-format whole when every editable target is safe to emit in
    # full. Whole-file output is far more reliable for local models than
    # diff/SEARCH/REPLACE: SEARCH/REPLACE requires either a valid empty SEARCH
    # block for brand-new files or a verbatim anchor into an existing file — both
    # protocols sub-frontier models botch (the canonical failure: one import line
    # repeated 175×), whereas whole just asks for the complete file. A target is
    # whole-safe if it is a freshly-created placeholder (new file) OR an existing
    # file small enough that reproducing it in full stays within the output/context
    # budget (<= WHOLE_FILE_MAX_LINES). Aider's --edit-format is per-invocation, not
    # per-file, so the whole step can only use whole if EVERY target qualifies: a
    # single oversized existing target forces the step onto diff (reproducing a
    # large file in full risks truncation and degenerate loops under the 10K-token
    # context window). The threshold mirrors PHASE1_SPEC's ~120-line per-step output
    # budget; override via PHASE2_WHOLE_FILE_MAX_LINES for stacks with verbose files.
    # Note this check is PER FILE, not aggregate: several sub-threshold targets can
    # together exceed the budget in one whole-format invocation. Bounding total
    # generation per step is the planner's job (PHASE1_SPEC §1 output budget), not
    # phase2.sh's — keep that enforcement in one place rather than splitting it here.
    WHOLE_FILE_MAX_LINES=${PHASE2_WHOLE_FILE_MAX_LINES:-120}
    # Validate the override: a non-integer value (typo, units like "120 lines",
    # stray spaces) would make the `-gt` test below error per file and — since
    # that test runs in an `if` condition, exempt from `set -e` — silently treat
    # every existing file as whole-safe, sending oversized files through the whole
    # format and reintroducing the degenerate loop this threshold exists to
    # prevent. Reject anything non-numeric (or zero) and fall back to the default.
    case "$WHOLE_FILE_MAX_LINES" in
        ''|*[!0-9]*|0)
            logf_err "==> WARN: ignoring invalid PHASE2_WHOLE_FILE_MAX_LINES='${WHOLE_FILE_MAX_LINES}' (must be a positive integer); using 120."
            WHOLE_FILE_MAX_LINES=120
            ;;
    esac
    EDIT_FMT_ARGS=()
    _file_target_count=$(( ${#FILE_ARGS[@]} / 2 ))
    _existing_target_count=${#_EXISTING_TARGETS[@]}
    _whole_safe=true
    _oversized_target=""
    _buildfile_target=""
    if [ "$_file_target_count" -eq 0 ]; then
        # No explicit targets: leave Aider on its default (diff). Forcing whole
        # with no --file args invites from-scratch hallucination.
        _whole_safe=false
    fi
    for _et in ${_EXISTING_TARGETS[@]+"${_EXISTING_TARGETS[@]}"}; do
        # An existing build file is never whole-safe regardless of size — the
        # observed corruption vector is whole-format regeneration re-emitting
        # (and mangling) dependency coordinates. See nimbus_is_build_file in
        # phase2-lib.sh.
        if nimbus_is_build_file "$_et"; then
            _whole_safe=false
            _buildfile_target="$_et"
            break
        fi
        # wc -l counts newlines, so a final line without a trailing newline is
        # uncounted — the count is a lower bound, which is fine for a threshold.
        _lc=$(wc -l < "$_et" 2>/dev/null | tr -cd '0-9')
        [ -z "$_lc" ] && _lc=0
        if [ "$_lc" -gt "$WHOLE_FILE_MAX_LINES" ]; then
            _whole_safe=false
            _oversized_target="$_et (${_lc} lines)"
            break
        fi
    done
    if [ "$_whole_safe" = true ]; then
        EDIT_FMT_ARGS=(--edit-format whole)
        if [ "$_existing_target_count" -eq 0 ]; then
            logf "==> All ${_file_target_count} editable target(s) are new placeholders — using Aider whole-file edit format (more robust for local models than diff/SEARCH/REPLACE on greenfield)."
        else
            logf "==> All ${_file_target_count} editable target(s) are new or <= ${WHOLE_FILE_MAX_LINES} lines — using Aider whole-file edit format (more reliable for local models than diff/SEARCH/REPLACE; verify.sh gates any dropped content)."
        fi
    elif [ -n "$_buildfile_target" ]; then
        logf "==> Existing build file ${_buildfile_target} is an edit target — using diff edit format for this step. Whole-file regeneration of a build file invites dependency-coordinate corruption (e.g. spring-boot-starter-parent -> spring-boot-starters-parent); keep the edit small and anchored on exact existing lines (see PHASE1_SPEC §Java)."
    elif [ -n "$_oversized_target" ]; then
        logf "==> Existing target ${_oversized_target} exceeds the ${WHOLE_FILE_MAX_LINES}-line whole-file threshold — using diff edit format for this step. Keep the edit small and give the model verbatim anchor text in the step file (see PHASE1_SPEC §1)."
    fi

    # Advisory: warn when a step targets more than one existing file that will be
    # edited via diff (i.e. the step fell back to diff because something was
    # oversized). A substantial existing-file rewrite under diff is the canonical
    # setup for a degenerate generation loop — the model spirals inside the
    # regenerated block. Suppressed when the step uses whole, since small existing
    # files emitted in full are not the looping risk. phase2.sh cannot tell a small
    # targeted edit from a full rewrite, so this is a heuristic nudge, not a gate.
    # Non-fatal; mirrors the token-cap warning. The planning rule is in PHASE1_SPEC
    # §1 (PLAN.md, "edit existing files"): shrink each edit to a targeted change
    # first, give verbatim anchors, and isolate any unavoidable full rewrite into
    # its own step — splitting alone does not prevent the loop.
    if [ "${#EDIT_FMT_ARGS[@]}" -eq 0 ] && [ "$_existing_target_count" -gt 1 ]; then
        logf_err "==> WARN: step targets ${_existing_target_count} existing files and is using diff edit format. Local models can loop regenerating large existing-file blocks. Prefer making each a small targeted edit with verbatim anchors rather than a full rewrite; isolate any unavoidable full rewrite into its own step (see PHASE1_SPEC §1)."
    fi

    # Dry run stops here: every pre-Aider check has passed (branch, dirty
    # tree, gate lint, endpoint preflight, planned-path parse, edit-format
    # decision). Exit before the watchdog config and WIP sentinel, which
    # write into .git/. Note dry-run classified missing planned files as
    # placeholders without creating them, so _PLACEHOLDERS names are
    # would-creates.
    if [ "$NIMBUS_MODE" = dryrun ]; then
        echo "==> DRY RUN complete — all pre-Aider checks passed for step $NEXT."
        echo "    A real run would invoke aider on $STEP_FILE with:"
        echo "      targets:     $(( ${#FILE_ARGS[@]} / 2 )) --file arg(s)${_PLACEHOLDERS[0]:+ (${#_PLACEHOLDERS[@]} would-be placeholder(s))}"
        echo "      edit format: ${EDIT_FMT_ARGS[1]:-diff (aider default)}"
        if [ "$FALLBACK_ACTIVE" = true ]; then
            echo "      model:       $PHASE2_FALLBACK_MODEL (fallback escalation armed)"
        fi
        exit 0
    fi

    # Live degenerate-output watchdog config. A local model can loop emitting the
    # same token sequence (import lines, class names) until the inference server
    # aborts — wasting the whole timeout window first. WATCHDOG_MAX is the number
    # of consecutive identical non-trivial (>10 char) output lines that count as a
    # loop. The watchdog needs `tail -F` (follow-by-name with retry) to read the
    # log Aider is writing and `pgrep` to find aider's children for the kill; if
    # either is missing it is disabled and the post-Aider guard below still
    # catches the (slower) exit-0 case. Detection uses a bash `read` loop rather
    # than awk on purpose: the common awk (mawk) block-buffers pipe input and
    # never processes tail -F's trickle until EOF, which never comes — so awk
    # would miss the loop entirely. WIP_FILE lives in .git/; reuse that dir.
    WATCHDOG_MAX=30
    WATCHDOG_MARKER=".git/phase2-watchdog-step${STEP_PAD}"
    rm -f "$WATCHDOG_MARKER"
    WATCHDOG_OK=false
    if command -v tail >/dev/null 2>&1 && command -v pgrep >/dev/null 2>&1; then
        WATCHDOG_OK=true
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
        ${MODEL_OVERRIDE_ARGS[@]+"${MODEL_OVERRIDE_ARGS[@]}"} \
        --no-auto-commits \
        --no-show-model-warnings \
        --map-tokens 0 \
        --no-suggest-shell-commands \
        --read "$STEP_FILE" \
        --read CONTEXT.md \
        ${FILE_ARGS[@]+"${FILE_ARGS[@]}"} \
        ${EDIT_FMT_ARGS[@]+"${EDIT_FMT_ARGS[@]}"} \
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

    # Watchdog subshell: follow the log Aider is appending to (starting at the
    # current end, so prior verify output on the recovery path is not counted).
    # When the read loop sees WATCHDOG_MAX identical non-trivial (>10 char,
    # trailing whitespace ignored) lines in a row, it writes the marker and kills
    # the aider tree FROM INSIDE THE LOOP, then exits — it does not wait for the
    # tail|loop pipeline to drain. That matters because tail -F only dies on its
    # next write (SIGPIPE), which may never come if output stalls right at the
    # threshold; acting inside the loop makes detection immediate. Writing the
    # marker only on this genuine-detection branch also avoids false positives:
    # on a normal finish the main shell SIGKILLs this subshell mid-read, so the
    # threshold branch never runs and no marker is written.
    _WATCHDOG_SUBSHELL=""
    if [ "$WATCHDOG_OK" = true ]; then
        (
          tail -n 0 -F "$LOG_FILE" 2>/dev/null | {
              _wprev=""; _wn=0
              while IFS= read -r _wline; do
                  _wline="${_wline%"${_wline##*[![:space:]]}"}"   # strip trailing whitespace
                  [ "${#_wline}" -gt 10 ] || continue
                  if [ "$_wline" = "$_wprev" ]; then
                      _wn=$((_wn + 1))
                      if [ "$_wn" -ge "$WATCHDOG_MAX" ]; then
                          printf 'x' > "$WATCHDOG_MARKER" 2>/dev/null || true
                          _kill_tree "$_AIDER_SUBSHELL"
                          exit 42
                      fi
                  else
                      _wprev="$_wline"; _wn=1
                  fi
              done
          }
        ) &
        _WATCHDOG_SUBSHELL=$!
    fi

    wait "$_AIDER_SUBSHELL"
    AIDER_EXIT=$?
    # Tear down the watchdog and its tail/read-loop children. On a clean finish this
    # SIGKILLs the watchdog mid-read before it reaches the threshold branch; if it
    # already fired, this is a harmless no-op. `wait` reaps the killed subshell.
    if [ -n "$_WATCHDOG_SUBSHELL" ]; then
        _kill_tree "$_WATCHDOG_SUBSHELL"
        wait "$_WATCHDOG_SUBSHELL" 2>/dev/null || true
        _WATCHDOG_SUBSHELL=""
    fi
    set -e

    # Watchdog fired: a degenerate generation loop was caught live and the aider
    # tree was killed. Report and bail before the generic exit-code checks — the
    # exit code reflects our kill, not aider's own outcome.
    if [ -f "$WATCHDOG_MARKER" ]; then
        rm -f "$WATCHDOG_MARKER"
        logf "==> Degenerate model output detected (watchdog: a non-trivial line repeated ${WATCHDOG_MAX}× in a row) — step $NEXT NOT recorded." \
             "    The local model looped emitting identical lines; aborted live to spare the 15-minute timeout window." \
             "    This is a model/cache QUALITY failure. Inspect $LOG_FILE. If repetition_penalty/DRY are already on and it still loops, the usual culprit is a low-bit quantized KV cache (cache_mode 2/3-bit) — move to 8,8 or FP16, disable reasoning/thinking for execution, or use a stronger/coder model. Splitting the step is only a stopgap."
        _cleanup_empty_placeholders
        _mark_step_failed
        rm -f "$WIP_FILE"
        exit 1
    fi

    # 124 = SIGTERM from timeout; 137 = SIGKILL from --kill-after (128 + 9).
    if { [ "$AIDER_EXIT" -eq 124 ] || [ "$AIDER_EXIT" -eq 137 ]; } && [ "${#TIMEOUT_CMD[@]}" -gt 0 ]; then
        logf "==> Aider hit the 15-minute timeout — step $NEXT NOT recorded. Inspect $LOG_FILE."
        _cleanup_empty_placeholders
        _mark_step_failed
        exit 1
    fi

    if [ "$AIDER_EXIT" -ne 0 ]; then
        logf "==> Aider exited $AIDER_EXIT — step $NEXT NOT recorded."
        _cleanup_empty_placeholders
        _mark_step_failed
        exit "$AIDER_EXIT"
    fi

    # Token-limit guard: some local models emit a "token limit" message and still
    # exit 0, but produce a truncated or malformed response. Crucially, two very
    # different failures both surface as "token limit" and must NOT be conflated:
    #
    #   (a) INPUT/context overflow — the prompt (CONTEXT.md + step file + target
    #       files) genuinely did not fit. Fix by reducing input.
    #   (b) OUTPUT truncation (finish_reason=length) — the *response* was cut off
    #       at the output budget. aider prints "has hit a token limit" for ANY
    #       finish_reason=length, so this looks identical to (a) but the input was
    #       usually nowhere near the limit. The common driver on a low-bit
    #       quantized KV cache is a DEGENERATE REPETITION LOOP that burns the
    #       output budget on garbage — a model/cache QUALITY problem, not a size
    #       one. Telling the user to "reduce CONTEXT.md" here sends them down the
    #       wrong path (this is exactly how the 0529 Step 3 failure was misread).
    #
    # Classify the two cases and give guidance that matches the actual cause.
    if [ -f "$LOG_FILE" ]; then
        if nimbus_log_input_overflow "$LOG_FILE"; then
            logf "==> INPUT exceeded the model's context window — step $NEXT NOT recorded." \
                 "    The prompt (CONTEXT.md + step file + target files) was too large to fit." \
                 "    Inspect $LOG_FILE. Reduce CONTEXT.md, shorten this step's 'Files to change' list, or raise max_seq_len/cache_size on the inference server."
            _cleanup_empty_placeholders
            _mark_step_failed
            rm -f "$WIP_FILE"
            exit 1
        fi
        if nimbus_log_token_limit "$LOG_FILE"; then
            # Did a single non-trivial line dominate the output? If so the model
            # looped and the cap merely terminated it — quality, not size.
            _rep=$(nimbus_log_max_total_repeat "$LOG_FILE")
            if [ "${_rep:-0}" -ge "$WATCHDOG_MAX" ]; then
                logf "==> OUTPUT truncated at the token cap AFTER a degenerate repetition loop (a line repeated ${_rep}×) — step $NEXT NOT recorded." \
                     "    This is a model/cache QUALITY failure, not a size problem: the model looped on repeated/garbage lines and the max_tokens cap ended it." \
                     "    Inspect $LOG_FILE. Raising max_tokens alone will likely just yield a LONGER broken file. Prefer: move off a low-bit KV cache (e.g. cache_mode 2/3-bit -> 8,8 or FP16), disable reasoning/thinking for execution, or use a stronger/coder model. Splitting the step is only a stopgap."
            else
                logf "==> OUTPUT hit the token cap (finish_reason=length) with no obvious loop — step $NEXT NOT recorded." \
                     "    The generation was legitimately larger than the output budget." \
                     "    Inspect $LOG_FILE. Raise the server max_tokens cap and/or split this step so it generates fewer/smaller files per run. Input/CONTEXT.md size is usually NOT the issue here."
            fi
            _cleanup_empty_placeholders
            _mark_step_failed
            rm -f "$WIP_FILE"
            exit 1
        fi
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
        # Match the live watchdog's semantics: longest run of CONSECUTIVE
        # identical non-trivial lines, not total occurrences — see
        # nimbus_log_max_repeat in phase2-lib.sh for why.
        _repeat_max=$(nimbus_log_max_repeat "$LOG_FILE")
        if [ "${_repeat_max:-0}" -ge "$WATCHDOG_MAX" ]; then
            logf "==> Degenerate model output detected (a line repeated ${_repeat_max}× in log) — step $NEXT NOT recorded." \
                 "    The local model likely looped generating the same tokens until the inference server aborted." \
                 "    Inspect $LOG_FILE. Consider splitting this step or using a stronger model." \
                 "    (The live watchdog normally catches this sooner; this backstop fires when Aider buffered the output and still exited 0.)"
            _cleanup_empty_placeholders
            _mark_step_failed
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
        logf_err "==> WARN: Aider internal failure detected (summarization error or exception) — see $LOG_FILE." \
                 "    Proceeding to verify.sh; if it fails, Aider may have produced partial output."
    fi

    # Remove any placeholder we created for a missing planned file that Aider
    # left empty, so the existence guard below surfaces the model's failure
    # rather than treating a 0-byte stub as "created". Populated placeholders
    # are kept for the commit on the success path.
    _cleanup_empty_placeholders

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
        logf "==> Step $NEXT halted: $HALT_FILE was written by the executor." \
             "    Discarding any unrelated in-tree changes from this run." \
             "    Review the halt report, fix the upstream gap, then re-run ./phase2.sh."
        git reset -q HEAD -- . 2>/dev/null || true    # unstage everything
        git add -- "$HALT_FILE"                       # restage only the halt file
        # Routing row is appended and staged BEFORE the commit so the halt
        # commit leaves a clean tree (see the success-path note on ordering).
        log_routing "step-${STEP_PAD}" "false" "0" "halted"
        git add -- "$ROUTING_LOG" 2>/dev/null || true
        git commit -m "Step $NEXT: HALT (missing prior artifact)"
        git checkout -- . 2>/dev/null || true         # discard tracked-file edits
        git clean -fd 2>/dev/null || true             # remove untracked, non-ignored files
        rm -f "$WIP_FILE" "$FAIL_MARKER"
        exit 2
    fi

    # Repair required .gitignore entries BEFORE the no-change guard below:
    # if Aider's only output was corrupting .gitignore, that guard exits 1
    # (correctly — a repaired ignore file is not step progress, which is why
    # _NOCHANGE_EXCLUDES keeps excluding .gitignore), and a repair placed
    # after it would never run, leaving the plans/*.log rule lost.
    _repair_gitignore

    # Guard against aider exiting 0 without touching anything (e.g. unreachable model, bad API key).
    # If no files changed, the model was never reached — do not mark the step done.
    # Use `git status --porcelain` (not `git diff`) so newly created *untracked*
    # files count as changes — a greenfield step that only creates new files
    # (e.g. populated placeholders Aider did not git-add) would otherwise be seen
    # as "no changes" and wrongly rejected. Uses _NOCHANGE_EXCLUDES (= commit
    # excludes plus .gitignore) so a housekeeping-only .gitignore edit — e.g.
    # Aider's startup rewrite — does NOT masquerade as real work and let a
    # zero-edit run reach verify.sh and be recorded DONE.
    if [ -z "$(git status --porcelain -- '.' "${_NOCHANGE_EXCLUDES[@]}" 2>/dev/null)" ]; then
        logf "==> Aider made no changes — model may not have been reached (check API key / endpoint). Step $NEXT NOT recorded."
        # Nothing real happened, so fully disarm the recovery machinery.
        # Discard any housekeeping-only .gitignore edit (Aider corruption
        # and/or our repair — HEAD's copy is authoritative when no real work
        # landed) and clear the WIP sentinel. Leaving the sentinel armed let
        # the next run take the preflight-verify recovery path, skip Aider,
        # and commit the step DONE with zero real changes (verify.sh can pass
        # trivially — e.g. the stack sentinel file does not exist yet); leaving
        # .gitignore dirty would block the next run's dirty-tree guard instead.
        git checkout -- .gitignore 2>/dev/null || true
        _mark_step_failed
        rm -f "$WIP_FILE"
        exit 1
    fi

fi

# Halt detection — recovery path: inside SKIP_AIDER=false the halt check fires
# if Aider wrote the halt file during this run (the inner halt block above). But
# if that run was killed between halt-file creation and the halt commit, the WIP
# sentinel persists and the next invocation takes the SKIP_AIDER=true path,
# bypassing the inner block entirely. This outer check catches that case so the
# halt report is always committed and exit 2 is always returned on a halt.
# On the SKIP_AIDER=false path this check is unreachable: the inner halt block
# already exited 2 before we reach here.
if [ -n "$(git status --porcelain -- "$HALT_FILE" 2>/dev/null)" ]; then
    logf "==> Step $NEXT halted (recovery): $HALT_FILE was written by the prior run." \
         "    Discarding any unrelated in-tree changes." \
         "    Review the halt report, fix the upstream gap, then re-run ./phase2.sh."
    git reset -q HEAD -- . 2>/dev/null || true
    git add -- "$HALT_FILE"
    log_routing "step-${STEP_PAD}" "false" "0" "halted"
    git add -- "$ROUTING_LOG" 2>/dev/null || true
    git commit -m "Step $NEXT: HALT (missing prior artifact)"
    git checkout -- . 2>/dev/null || true
    git clean -fd 2>/dev/null || true
    rm -f "$WIP_FILE" "$FAIL_MARKER"
    exit 2
fi

# Recovery-path .gitignore repair: the SKIP_AIDER=false path repairs before its
# no-change guard (see above); this call covers the SKIP_AIDER=true recovery
# path, which bypasses that block entirely. Idempotent, so the double call on
# the normal path is a no-op.
_repair_gitignore

# Malformed-path guard runs BEFORE the planned-file existence check so that
# garbage files Aider created at bad paths are cleaned up first. Without this
# ordering, a garbage-path artifact would cause the existence guard to fire
# and exit 1 before git clean runs, leaving the garbage file in the working
# tree and causing the next invocation's dirty-tree guard to block.
# Two patterns are caught: the literal '**' artifact, and a dotted directory
# component under a JVM source root (com.example as a directory instead of
# com/example) — the package-name-as-directory bug a local executor produces
# when a step leaves the layout implicit. See PHASE1_SPEC §Java.
#
# `--untracked-files=all` is REQUIRED: by default `git status --porcelain`
# collapses an entirely-untracked subtree to its top component (a brand-new
# `src/main/java/com.example/Foo.java` in a greenfield step where nothing under
# src/ is tracked shows only as `?? src/`), so the dotted segment never reaches
# grep and the guard silently misses it. `-uall` expands to individual files.
#
# Status is captured ONCE (one porcelain walk, not one per pattern) and reduced
# to the effective on-disk path per entry before grepping: the 2-char status
# code + space prefix is stripped, and for a rename/copy entry (`OLD -> NEW`)
# only NEW — the path that now exists — is kept. Without this the guard would
# fire on the OLD half of a *corrective* rename (e.g. fixing com.example/ ->
# com/example/) and discard the very fix it should reward.
_ST=$(git status --porcelain --untracked-files=all -- '.' "${_BUILD_EXCLUDES[@]}" 2>/dev/null || true)
_EFF=$(printf '%s\n' "$_ST" | sed -e 's/^...//' -e 's/^.* -> //')
_MP=$(printf '%s\n' "$_EFF" | grep -E '\*\*' || true)
_MP_PKG=$(printf '%s\n' "$_EFF" | grep -E "$_JVM_DOTTED_DIR_RE" || true)
if [ -n "$_MP" ] || [ -n "$_MP_PKG" ]; then
    logf "==> ERROR: files with malformed paths detected — likely model output artifact. Step $NEXT NOT recorded."
    if [ -n "$_MP" ]; then
        logf "    Pattern '**' found in the following working-tree paths:"
        while IFS= read -r _mpl; do logf "    $_mpl"; done <<< "$_MP"
    fi
    if [ -n "$_MP_PKG" ]; then
        logf "    A directory segment under a JVM source root (src/main|test/java, ...) contains a '.'," \
             "    which is almost certainly a package-name-as-directory bug: a Java/Kotlin package maps to" \
             "    directories by replacing '.' with '/' (com.example.app -> com/example/app). Affected paths:"
        while IFS= read -r _mpl; do logf "    $_mpl"; done <<< "$_MP_PKG"
    fi
    logf "    Discarding malformed files and resetting working tree."
    # Unstage FIRST: Aider stages the new files it creates, and neither
    # `git checkout -- .` (restores from the index, which still holds them)
    # nor `git clean -fd` (skips index-tracked paths) touches staged new
    # files — without the reset they survive cleanup and wedge later runs.
    git reset -q HEAD -- . 2>/dev/null || true
    git checkout -- . 2>/dev/null || true
    git clean -fd 2>/dev/null || true
    _mark_step_failed
    rm -f "$WIP_FILE"
    exit 1
fi

# Build-file coordinate-corruption guard: when a local model regenerates
# pom.xml / build.gradle it can corrupt well-known coordinates by a few
# characters. Those near-miss names resolve to nothing, but only a CORRECT
# verify.sh catches that — and a buggy generated gate is exactly how one such
# pom shipped as a "passing" step. This static guard rejects the known
# corruption class (see _BUILD_COORD_CORRUPTION_RE in phase2-lib.sh) before
# verify.sh ever runs, independent of the generated gate's quality. Only build
# files touched THIS run are inspected; pre-existing content is not this
# step's responsibility.
_CORRUPT_BUILD_FILES=()
for _bf in pom.xml build.gradle build.gradle.kts settings.gradle settings.gradle.kts; do
    [ -f "$_bf" ] || continue
    [ -n "$(git status --porcelain -- "$_bf" 2>/dev/null)" ] || continue
    if nimbus_has_corrupt_build_coords "$_bf"; then
        _CORRUPT_BUILD_FILES+=("$_bf")
    fi
done
if [ "${#_CORRUPT_BUILD_FILES[@]}" -gt 0 ]; then
    logf "==> ERROR: corrupted dependency coordinates detected — step $NEXT NOT recorded."
    for _bf in "${_CORRUPT_BUILD_FILES[@]}"; do
        logf "    $_bf matches '${_BUILD_COORD_CORRUPTION_RE}' — a near-miss corruption of a" \
             "    spring-boot-starter-* coordinate (e.g. spring-boot-starters-parent," \
             "    spring-boot-started-web). These artifacts do not exist and cannot resolve."
    done
    logf "    Discarding this run's changes and resetting working tree." \
         "    This is a model-output QUALITY failure — see the serving checklist in" \
         "    .aider.conf.yml / docs/tabbyapi-nimbus-example.yml before retrying."
    git reset -q HEAD -- . 2>/dev/null || true
    git checkout -- . 2>/dev/null || true
    git clean -fd 2>/dev/null || true
    _mark_step_failed
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
done < <(nimbus_planned_entries "$STEP_FILE")
if [ "${#_MISSING_PLANNED[@]}" -gt 0 ]; then
    logf "==> ERROR: planned file(s) missing — step $NEXT NOT recorded."
    for _m in "${_MISSING_PLANNED[@]}"; do logf "    missing: $_m"; done
    if [ "$SKIP_AIDER" = true ]; then
        # Recovery path: the prior Aider run may have left partial changes.
        # Preserve WIP_FILE when the tree is dirty so the next invocation retries
        # the SKIP_AIDER=true path — if verify.sh then fails, SKIP_AIDER flips to
        # false and Aider re-runs to complete the step. When the tree is clean
        # (Aider was killed before writing anything), remove WIP_FILE so the next
        # invocation runs Aider fresh instead of looping through SKIP_AIDER=true.
        # _COMMIT_EXCLUDES, not _BUILD_EXCLUDES: this run's own $LOG_FILE is
        # untracked whenever .gitignore lost its plans/*.log rule, and would
        # otherwise make every recovery run look "dirty".
        _RECOVERY_DIRTY=$(git status --porcelain -- '.' "${_COMMIT_EXCLUDES[@]}" 2>/dev/null || true)
        if [ -n "$_RECOVERY_DIRTY" ]; then
            logf "    The prior Aider run left uncommitted partial changes in the working tree." \
                 "    Re-run ./phase2.sh — if verify.sh fails, Aider will be re-invoked to" \
                 "    complete the step. To discard partial changes and start fresh:" \
                 "      git checkout -- . && git clean -fd && rm -f '${WIP_FILE}'"
        else
            logf "    The prior Aider run appears to have made no changes. Re-running" \
                 "    ./phase2.sh will invoke Aider fresh to complete the step."
            rm -f "$WIP_FILE"
        fi
    else
        logf "    Aider may have skipped creating these paths. Inspect $LOG_FILE." \
             "    Note: non-parenthesis annotations (em-dash, colon) on list entries are" \
             "    not stripped and cause the entry to be silently skipped. Use '(note)' format."
        rm -f "$WIP_FILE"
    fi
    exit 1
fi

# Model-artifact scrubber: local models emitting whole-file edits sometimes wrap
# file content in markdown code fences (```), writing the literal fence characters
# into source files. Strip any line that is a markdown code fence (3+ backticks
# only) and bare file-path leak lines (e.g. `src/main/java/Foo.java` alone on a
# line — the next file's header that bled into the current file's content).
# NOTE: the fence pattern requires 3+ backticks on purpose. A single backtick on
# its own line is valid source — a Go raw-string delimiter or a JS/TS multi-line
# template-literal delimiter — and both extensions are in the scrub list, so
# matching `+ (one-or-more) would silently corrupt valid code. Markdown fences are
# always 3+ backticks, so `{3,} catches the artifact without that false positive.
_SCRUB_EXTS_RE='\.(java|kt|scala|groovy|py|ts|tsx|js|jsx|go|rs|rb|cs|cpp|c|h)$'
_SCRUBBED=()
while IFS= read -r _pf; do
    _ppath=$(_strip_md_path "$_pf")
    [ -z "$_ppath" ] && continue
    case "$_ppath" in *" "*) continue ;; esac
    [[ "$_ppath" =~ $_SCRUB_EXTS_RE ]] || continue
    [ -f "$_ppath" ] || continue
    _before=$(wc -l < "$_ppath" | tr -d '[:space:]')
    _tmp=$(mktemp)
    grep -Ev \
        '^[[:space:]]*`{3,}[[:space:]]*$|^[[:space:]]*(src|test|main|lib|app)/[^[:space:]]+\.(java|kt|scala|groovy|py|ts|tsx|js|jsx|go|rs|rb|cs|cpp|c|h)[[:space:]]*$' \
        "$_ppath" > "$_tmp" || true
    _after=$(wc -l < "$_tmp" | tr -d '[:space:]')
    if [ "$_before" -ne "$_after" ]; then
        mv "$_tmp" "$_ppath"
        _SCRUBBED+=("$_ppath (removed $((_before - _after)) artifact line(s))")
    else
        rm -f "$_tmp"
    fi
done < <(nimbus_planned_entries "$STEP_FILE")
if [ "${#_SCRUBBED[@]}" -gt 0 ]; then
    logf "==> Scrubbed model artifact line(s) from source files before verify.sh:"
    for _s in "${_SCRUBBED[@]}"; do logf "    $_s"; done
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
    logf_err "==> WARN: tee failed writing $LOG_FILE (exit ${_verify_tee_rc} — disk full?)"
fi
if [ "$VERIFY_EXIT" -eq 0 ]; then
    [ -f CompletedSteps.md ] || echo "# Completed Steps" > CompletedSteps.md
    echo "Step $NEXT: DONE" >> CompletedSteps.md
    git add -A -- '.' "${_COMMIT_EXCLUDES[@]}"
    # Stage first, measure the staged diff, THEN append the routing row and
    # stage it too, so the step commit includes its own bookkeeping. Appending
    # after the commit (the old order) left logs/ai-routing.csv dirty after
    # every "successful" step — tripping the next run's dirty-tree guard and
    # forcing extra bookkeeping-only commits.
    DIFF_LINES=$(git diff --cached --numstat 2>/dev/null | awk '{a+=$1+$2} END {print a+0}')
    log_routing "step-${STEP_PAD}" "true" "${DIFF_LINES:-0}" "done"
    git add -- "$ROUTING_LOG" 2>/dev/null || true
    git commit -m "Step $NEXT: complete"
    rm -f "$WIP_FILE" "$FAIL_MARKER"
    logf "==> Step $NEXT committed."
else
    logf "==> verify.sh failed after aider exited — step $NEXT NOT recorded."
    _mark_step_failed
    exit 1
fi
