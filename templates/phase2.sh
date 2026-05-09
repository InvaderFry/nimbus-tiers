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
    else
        echo "All steps complete — no step file found at $STEP_FILE"
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
