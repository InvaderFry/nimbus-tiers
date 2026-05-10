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

# Bound retries (--max-reflections 3) and wall-clock (timeout 15m). Together
# they cap the blast radius of a fundamentally underspecified step.
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

AIDER_EXIT=0
"${TIMEOUT_CMD[@]}" aider \
  --no-auto-commits \
  --max-reflections 3 \
  --read "$STEP_FILE" \
  --read CONTEXT.md \
  --test-cmd "./verify.sh" \
  --auto-test \
  --yes \
  -m "Implement only the step in $STEP_FILE. CONTEXT.md has invariants and do-not-change areas. Run ./verify.sh; if it fails, fix and retry." \
  2>&1 | tee "$LOG_FILE" || true
AIDER_EXIT="${PIPESTATUS[0]}"

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
    exit 2
fi

# Guard against aider exiting 0 without touching anything (e.g. unreachable model, bad API key).
# If no files changed, the model was never reached — do not mark the step done.
if git diff --quiet && git diff --cached --quiet; then
    echo "==> Aider made no changes — model may not have been reached (check API key / endpoint). Step $NEXT NOT recorded."
    exit 1
fi

# Shell owns bookkeeping — runs after aider exits, independently of whether aider's
# internal summarization completed. Prevents lost progress on aider crashes post-verification.
if ./verify.sh; then
    [ -f CompletedSteps.md ] || echo "# Completed Steps" > CompletedSteps.md
    echo "Step $NEXT: DONE" >> CompletedSteps.md
    git add -A
    git commit -m "Step $NEXT: complete"
    DIFF_LINES=$(git show --numstat HEAD 2>/dev/null | awk '{a+=$1+$2} END {print a+0}')
    log_routing "step-${STEP_PAD}" "true" "${DIFF_LINES:-0}" "done"
    echo "==> Step $NEXT committed."
else
    echo "==> verify.sh failed after aider exited — step $NEXT NOT recorded."
    exit 1
fi
