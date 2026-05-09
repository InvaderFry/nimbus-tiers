# CLAUDE.md — {{PROJECT_NAME}}

> Project memory for Claude Code. This repo follows the **Hybrid AI Coding Architecture** — see [`docs/architecture.md`](./docs/architecture.md) for the full spec.

## Workflow: Plan → Execute → Review

This repo uses four handoff artifacts:

- **`PLAN.md`** — human-readable feature overview (gitignored by default; for humans and Phase 3 review)
- **`TESTS.md`** — full acceptance test checklist (gitignored by default; for Phase 3 review)
- **`plans/step01.md` … `stepNN.md`** — one file per step; the only plan files the executor reads
- **`CONTEXT.md`** — invariants, contracts, and do-not-change areas (committed)
- **`VERIFY.md`** — repo-level definition of "done" (committed)

When you start a new feature:

1. **Phase 1 (Planning, you):** Use plan mode to read the codebase, then write `PLAN.md`, `TESTS.md`, per-step files in `plans/`, and update `CONTEXT.md` if anything new emerged.
2. **Phase 2 (Execution, local):** The user runs `./phase2.sh`, which feeds one step file at a time to Aider + local Qwen3-32B. Each run commits one step and stops.
3. **Phase 3 (Review, you):** Compare the diff to `PLAN.md`, `TESTS.md`, `CONTEXT.md`. Run `VERIFY.md`. Produce a numbered fix list or `APPROVED`.

## Routing rules

When the user asks for help, route per the architecture decision tree:

- **Planning / architecture / final review** → you (frontier).
- **Trivial tasks** (regex, format conversion, single-line) → suggest Tier 0 (Groq small model via Aider mid-session swap) or just answer directly.
- **Bulk execution against a clear plan** → defer to Tier 1 (local Aider). Don't ghost-write large diffs in this conversation; produce the PLAN.md instead.
- **Privacy-sensitive code** → local only. Do not include sensitive content in your responses or suggestions to escalate.

## Plan-mode prompt template

```
Don't write code yet. Read the relevant files, understand the architecture,
and produce a numbered implementation plan for [feature/task].

For each step, specify:
1. Which file(s) to modify
2. What change to make
3. What the change should accomplish
4. Edge cases to handle
5. Tests to write for that step

Be specific enough that a less capable engineer (the local executor) could
execute each step without re-reading the codebase.

When done:
- Write the full plan overview to PLAN.md (create or overwrite).
- Write the full acceptance test checklist to TESTS.md (create or overwrite).
- Write one file per step to plans/step01.md, step02.md, etc. Each file must
  be self-contained (file(s) to edit, what to do, edge cases, acceptance tests
  for that step only) and under ~400 tokens. These are the only files the
  executor reads — PLAN.md and TESTS.md are for humans and Phase 3 review.
- If new invariants, public contracts, or do-not-touch areas surfaced, append
  them to CONTEXT.md.
- Do not write any implementation code in this session.
```

## Review-mode prompt template

```
Review the diff between [base-commit] and HEAD against PLAN.md, TESTS.md,
and CONTEXT.md. Check for:

1. Did each step get implemented as specified in PLAN.md?
2. Are all tests from TESTS.md present and passing?
3. Were all invariants and constraints in CONTEXT.md respected?
4. Bugs, edge cases, security issues
5. Style/consistency with the rest of the codebase
6. Performance regressions
7. Any deviations from the plan that need justification

Produce a numbered list of required fixes, ordered by severity. If no fixes
needed, say "APPROVED" and provide a one-paragraph commit-message summary.
```

## Repo conventions

- _Add project-specific conventions here as the codebase evolves: package layout, naming, preferred libraries, deployment targets, etc._

## Out of scope for AI execution

- Anything in the `Do-not-change areas` section of `CONTEXT.md`.
- Anything listed under "Human review required" in `VERIFY.md`.
