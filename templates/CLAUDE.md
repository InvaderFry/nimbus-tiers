# CLAUDE.md — {{PROJECT_NAME}}

> Project memory for Claude Code. This repo follows the **Hybrid AI Coding Architecture** — see [`docs/architecture.md`](./docs/architecture.md) for the full spec.

## Workflow: Plan → Execute → Review

This repo uses the following handoff artifacts:

- **`PHASE1_SPEC.md`** — canonical spec for Phase 1 output. Single source of truth. (committed)
- **`PLAN.md`** — human-readable feature overview (gitignored by default; for humans and Phase 3 review)
- **`TESTS.md`** — full acceptance test checklist (gitignored by default; for Phase 3 review)
- **`plans/step01.md` … `stepNN.md`** — one file per step; the only plan files the executor reads
- **`plans/halt-stepNN.md`** — written by the executor when a required prior artifact is missing; triggers exit code 2 from `phase2.sh`
- **`CONTEXT.md`** — invariants, contracts, and do-not-change areas (committed)
- **`VERIFY.md`** — repo-level definition of "done" (committed)
- **`PHASE1_VERIFY_HELPER.md`** — stack-specific quiet-log snippet for `verify.sh`
- **`CompletedSteps.md`** — step completion log written and committed by `phase2.sh` (committed, not gitignored)

When you start a new feature:

1. **Phase 1 (Planning, you):** Read `PHASE1_SPEC.md` and follow it exactly. Use plan mode to read the codebase, then produce the artifacts named in that spec (`PLAN.md`, `TESTS.md`, `VERIFY.md`, `verify.sh`, per-step files in `plans/`, and `CONTEXT.md` updates if anything new emerged). If the user's project inputs are sparse or ambiguous, ask before writing anything.
2. **Phase 2 (Execution, local):** The user runs `./phase2.sh`, which feeds one step file at a time to Aider + local Qwen3-32B with a 15-minute wall-clock timeout. Each successful run commits one step and stops; halts produce exit code 2.
3. **Phase 3 (Review, you):** Compare the diff to `PLAN.md`, `TESTS.md`, `CONTEXT.md`. Run `VERIFY.md`. Produce a numbered fix list or `APPROVED`.

## Routing rules

When the user asks for help, route per the architecture decision tree:

- **Planning / architecture / final review** → you (frontier).
- **Trivial tasks** (regex, format conversion, single-line) → suggest Tier 0 (Groq small model via Aider mid-session swap) or just answer directly.
- **Bulk execution against a clear plan** → defer to Tier 1 (local Aider). Don't ghost-write large diffs in this conversation; produce the PLAN.md instead.
- **Privacy-sensitive code** → local only. Do not include sensitive content in your responses or suggestions to escalate.

## Plan-mode prompt template

The full Phase 1 specification lives in `PHASE1_SPEC.md`. The plan-mode
prompt is a thin shell that points Claude at the spec and supplies the
per-feature inputs. The detailed starter prompt is in `NIMBUS_GUIDE.md`;
both this template and that one resolve to the same spec.

> **Two entry points are deliberate.** `CLAUDE.md` is auto-loaded by Claude
> Code on every session; `NIMBUS_GUIDE.md` is the human-facing onboarding
> doc with a worked example. They share `PHASE1_SPEC.md` so policy can't
> diverge — but if you edit either prompt shell, keep them aligned by
> updating the spec, not by widening the shells.

```
We are in Phase 1: planning and verification design only.

Read PHASE1_SPEC.md and follow it exactly. It defines the role, allowed
files, output schema, per-step token cap, halt semantics, and per-section
policy. Do not deviate from it.

Don't write any implementation code in this session. If any project input
below is missing or too vague to plan against, ask clarifying questions
before writing any artifact.

For verify.sh, inline the snippet from PHASE1_VERIFY_HELPER.md (which is
already specific to this project's stack).

[Then paste the FEATURE / TECH STACK / PROJECT STATE / OUTPUT-BEHAVIOR
CONTRACT / EXTERNAL DEPENDENCIES inputs — see NIMBUS_GUIDE.md for the
template and a worked example.]
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
