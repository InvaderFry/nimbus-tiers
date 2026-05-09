# plans/

This directory serves two purposes during the Plan → Execute → Review flow.

## 1. Active step files (Phase 2 input)

Phase 1 generates one file per implementation step:

```
plans/step01.md
plans/step02.md
plans/step03.md
...
```

Each file covers exactly one step: which file(s) to change, what to do, edge cases to handle, and acceptance tests for that step. These are the only plan files the executor (Aider + local model) reads — `PLAN.md` and `TESTS.md` are for humans and Phase 3 review only.

Keep each step file under ~400 tokens (roughly 300 words). The local model has a 10K token context window and needs headroom for its system prompt, `CONTEXT.md`, and `CompletedSteps.md`.

Run `./phase2.sh` to execute steps one at a time. It reads `CompletedSteps.md` to find the next unfinished step, loads only that step's file, and commits on success.

## 2. Completed feature archive (end of Phase 2)

When all steps are done, `phase2.sh` automatically archives `PLAN.md` here and removes the per-step files in a single commit. No manual step required.

The archive filename is derived from the current git branch:

```
plans/YYYY-MM-<branch-name>.md
```

`PLAN.md` stays in the repo root so Phase 3 review can still reference it.

### Why archive

- **Pattern reuse** — the next similar feature can crib structure from a past plan.
- **Postmortem signal** — when a review surfaces a systemic gap, the archived plan shows what the planner missed.
- **Onboarding** — new contributors see real examples of how features are scoped in this repo.

Keep the archived plan exactly as it was when execution started. If the plan changed mid-execution, append an "Amendments" section rather than editing earlier sections.
