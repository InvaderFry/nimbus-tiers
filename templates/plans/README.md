# plans/

Archive of completed `PLAN.md` files. When a feature ships, copy the working `PLAN.md` from the repo root into this directory with a dated filename:

```bash
cp PLAN.md plans/$(date +%Y-%m)-feature-name.md
```

## Why archive plans

- **Pattern reuse** — the next similar feature can crib structure from a past plan.
- **Postmortem signal** — when a review surfaces a systemic gap, the archived plan shows what the planner missed.
- **Onboarding** — new contributors see real examples of how features are scoped in this repo.

## Naming convention

`YYYY-MM-short-feature-name.md` — sortable, grep-able, no special characters.

## What to include

Keep the archived plan exactly as it was when execution started. Don't rewrite history. If the plan changed mid-execution, append an "Amendments" section at the bottom rather than editing earlier sections.
