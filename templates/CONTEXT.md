# CONTEXT.md — {{PROJECT_NAME}}

> Persistent context the executor (Aider/local model) must respect during Phase 2 (Execution). Update this file as the codebase evolves; keep it short and high-signal. Read-only in Aider sessions (`--read CONTEXT.md`).

## Relevant files

- `src/...` — _list the files most relevant to this repo's domain. Add a one-line description of what each does and why it matters._

## Known invariants

- _Rule the code must never violate. Examples: "user IDs are always UUIDs, never integers", "free tier users cannot have more than 3 active items"._

## Public API contracts

- `function_name(args) -> ReturnType` — _what callers expect; do not change the signature without a coordinated migration._
- _Any HTTP endpoint, CLI flag, or library export external systems depend on._

## Data model assumptions

- _Schema constraints the executor must respect._
- _Enum values that must stay stable._

## Style examples

- See `src/.../example.py` for the canonical pattern for this type of change.
- Naming convention: _e.g., "all event handlers are named `handle_X`"._

## Do-not-change areas

- `src/auth/` — any changes here require human review, not AI execution.
- `src/billing/` — same.
- _Specific functions or classes that are off-limits for the current task._

## Open questions

- _Anything unresolved that the executor should flag rather than guess at._

## Rollback plan

- _How to undo a typical change in this repo if something goes wrong post-merge (revert + redeploy? feature flag off? data backfill?)._
