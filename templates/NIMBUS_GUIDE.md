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
# paste the Phase 2 starter prompt below at the > prompt

# Phase 3 — find the base commit, then open Claude Code
git log --oneline   # copy the hash of the last commit before execution started
claude              # paste the Phase 3 starter prompt below, filling in that hash

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

### Phase 2 starter prompt

Paste this at the Aider `>` prompt after startup.

```
Execute the plan in PLAN.md step by step, starting with step 1.
Before editing any file, add it to the chat with /add <path>.
Make one commit per step using the step number as the commit message prefix (e.g. "Step 1: ...").
Do not skip steps or combine them.
```

### Phase 3 starter prompt

First get the base commit hash (the last commit **before** Aider started):

```bash
git log --oneline
```

Then paste this as your first message in a new Claude Code session, filling in the hash:

```
We are in Phase 3 (review only). Do not write any code.

Base commit: [paste hash here]

Review the diff from that commit to HEAD against PLAN.md, TESTS.md, and CONTEXT.md.

Check for:
1. Did each step get implemented as specified in PLAN.md?
2. Are all tests from TESTS.md present and passing?
3. Were all invariants and constraints in CONTEXT.md respected?
4. Bugs, edge cases, security issues
5. Style/consistency with the rest of the codebase
6. Performance regressions
7. Any deviations from the plan that need justification

Produce a numbered list of required fixes ordered by severity. If nothing needs
fixing, say APPROVED and provide a one-paragraph commit-message summary.
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
