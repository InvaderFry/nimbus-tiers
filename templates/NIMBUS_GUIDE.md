# {{PROJECT_NAME}}

Scaffolded from the [nimbus-tiers](https://github.com/invaderfry/nimbus-tiers) template. This project follows the **Hybrid AI Coding Architecture** — a three-phase Plan → Execute → Review flow that routes work across local models, free cloud APIs, and frontier subscriptions.

## The flow

| Phase | Tool | Output |
|---|---|---|
| 1. Plan | Claude Code (frontier) | `PLAN.md`, `TESTS.md`, updated `CONTEXT.md` |
| 2. Execute | Aider + local Qwen3-32B (TabbyAPI) | Series of git commits, one per step |
| 3. Review | Claude Code (frontier) | Fix list or `APPROVED` |

See [`docs/architecture.md`](./docs/architecture.md) for the full reference.

## Per-feature workflow

```bash
# Phase 1 — plan in Claude Code
claude            # paste the Phase 1 starter prompt below, then iterate

# Phase 2 — execute in Aider against local model
aider --read PLAN.md --read TESTS.md --read CONTEXT.md

# Phase 3 — review in Claude Code
claude            # run the review prompt from CLAUDE.md against the diff

# Final gate — run VERIFY.md before merge
```

### Phase 1 starter prompt

Copy this as your **first message** when opening a new Claude Code session for planning. Fill in the bracketed parts.

```
We are in Phase 1 (planning only). Do not write any implementation code.

Feature: [one-sentence description of what we're building or fixing]

Relevant files to read first:
- [path/to/file1] — [why it matters]
- [path/to/file2] — [why it matters]

Read CONTEXT.md and VERIFY.md for existing invariants and the definition of done.

Then produce a numbered implementation plan specific enough that a less
capable model can execute each step without re-reading the codebase. For
each step include: file(s) to change, what to change, what it accomplishes,
edge cases, and tests.

Write the plan to PLAN.md and the acceptance tests to TESTS.md. If new
invariants or do-not-touch areas emerge, append them to CONTEXT.md.
```

## Repo files

| File | Purpose |
|---|---|
| `CLAUDE.md` | Project memory for Claude Code (committed). |
| `CONTEXT.md` | Invariants, public contracts, do-not-touch areas (committed). |
| `VERIFY.md` | Repo-level definition of "done" (committed). |
| `PLAN.md` | Per-feature execution contract (gitignored). |
| `TESTS.md` | Per-feature acceptance tests (gitignored). |
| `plans/` | Archive of completed PLAN.md files for reference. |
| `logs/ai-routing.csv` | Lightweight metrics log of where work was routed. |
| `docs/architecture.md` | Full architecture reference. |
| `.aider.conf.yml` | Aider config (Path C defaults: local TabbyAPI). |
| `.aiderignore` | Files Aider must not read (secrets, env, credentials). |

## Quota budget (rough estimates)

- Plan: ~50K Claude tokens per feature.
- Execute: 0 Claude tokens (all local).
- Review: ~30K Claude tokens.
- Optional fix loop: ~30K.

If you find yourself escalating >30% of execution to cloud, your plans are not specific enough — invest more time in Phase 1.
