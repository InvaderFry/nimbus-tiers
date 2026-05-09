#!/usr/bin/env bash
# Phase 2 executor — runs one Aider step at a time against the local model.
# Re-run until all steps are complete; picks up where it left off via CompletedSteps.md.
# Usage: ./phase2.sh
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

STEP_FILE="plans/step$(printf '%02d' "$NEXT").md"

if [ ! -f "$STEP_FILE" ]; then
    if [ "$NEXT" -eq 1 ]; then
        echo "No step files found. Run Phase 1 first to generate plans/step01.md"
        exit 0
    fi

    echo "All steps complete."

    if [ -f "PLAN.md" ]; then
        BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null | sed 's|.*/||' || echo "plan")
        ARCHIVE="plans/$(date +%Y-%m)-${BRANCH}.md"
        echo "Archiving PLAN.md to $ARCHIVE"
        cp PLAN.md "$ARCHIVE"
        git add "$ARCHIVE"
        git commit -m "Archive PLAN.md to $ARCHIVE"
    fi

    exit 0
fi

echo "==> Step $NEXT: $STEP_FILE"

aider \
  --no-auto-commits \
  --read "$STEP_FILE" \
  --read CONTEXT.md \
  --test-cmd "./verify.sh" \
  --auto-test \
  CompletedSteps.md \
  --yes \
  -m "Read CompletedSteps.md (create with '# Completed Steps' if missing). \
Implement exactly the step described in $STEP_FILE — nothing more. \
Do not touch files not listed in that step. Do not refactor unrelated code. \
Use CONTEXT.md for project invariants and do-not-change areas. \
Run ./verify.sh. If it fails, stop — do not update CompletedSteps.md and do not commit. \
If ./verify.sh exits 0, append to CompletedSteps.md: 'Step $NEXT: DONE — <one-line summary>'. \
Then run: git add -A && git commit -m 'Step $NEXT: <one-line summary>'."
