# CLAUDE.md — {{PROJECT_NAME}}

> Project memory for Claude Code. This repo follows the **Hybrid AI Coding Architecture** — see [`docs/architecture.md`](./docs/architecture.md) for the full spec.

## Workflow: Plan → Execute → Review

This repo uses three handoff artifacts:

- **`PLAN.md`** — what to do, step by step (gitignored by default; per-feature)
- **`TESTS.md`** — what passing looks like (gitignored by default; per-feature)
- **`CONTEXT.md`** — invariants, contracts, and do-not-change areas (committed)
- **`VERIFY.md`** — repo-level definition of "done" (committed)

When you start a new feature:

1. **Phase 1 (Planning, you):** Use plan mode to read the codebase, then write `PLAN.md`, `TESTS.md`, and update `CONTEXT.md` if anything new emerged.
2. **Phase 2 (Execution, local):** The user runs Aider against a local model (Path C: TabbyAPI Qwen3-32B) with all three files in `--read` context.
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
5. Tests to write

Be specific enough that a less capable engineer (the local executor) could
execute each step without re-reading the codebase.

When done:
- Write the full plan to PLAN.md (create or overwrite).
- Write acceptance tests to TESTS.md (create or overwrite).
- If new invariants, public contracts, or do-not-touch areas surfaced, append
  them to CONTEXT.md.
- Do not write any implementation code in this session.
```

### Example

```
We are in Phase 1 (planning only). Do not write any implementation code.

---

FEATURE
Create a Java Spring Boot CommandLineRunner application that fetches the
current weather for Plano, Texas, prints it to the console, and writes
the same output to weather.txt in the project root directory, overwriting
the file on each execution. The process runs, outputs results, and exits with code 0.

TECH STACK
- Java 21
- Spring Boot 3.3.x
- Maven (the project uses the Maven wrapper: ./mvnw)

API
Pick a free weather API that doesn't need an API key.

OUTPUT FORMAT
Both the console and weather.txt must show these fields, one per line:
  Temperature:  <value> °F
  Condition:    <description, e.g. "Partly Cloudy">
  Humidity:     <value> %
  Wind Speed:   <value> mph
  Observed At:  <ISO-8601 timestamp>

PROJECT STATE
This is the first generation of this project. The directory contains only
nimbus-tiers scaffolding files (CONTEXT.md, VERIFY.md, CLAUDE.md,
.aider.conf.yml, etc.). There is no src/ directory, no pom.xml, and no
Java source. The plan must include a step to create the Spring Boot
project structure from scratch.

All content in CONTEXT.md, VERIFY.md, and CLAUDE.md is boilerplate from
the project generator. Treat every section as a template to be replaced
with project-specific content.

---

DELIVERABLES

1. PLAN.md — a numbered implementation plan specific enough that a less
   capable model can execute each step without re-reading the codebase.
   For each step include:
     - File(s) to create or modify
     - Exactly what to add or change
     - What the change accomplishes
     - Edge cases to handle (API timeout, non-200 response, file write
       failure, missing JSON fields)
     - Tests to write for that step

2. TESTS.md — acceptance criteria. Define what "done" looks like:
   specific inputs, expected console output, expected weather.txt content,
   and expected exit behavior. Include both the happy path and failure
   cases (API unreachable, partial response).

3. CONTEXT.md — replace the boilerplate with project-specific content:
   the chosen API endpoint and parameters, the output format as an
   invariant, and any do-not-change areas that emerge from the design.

4. VERIFY.md — replace the boilerplate. The test command must be
   ./mvnw test. Include any other checks required before a commit is
   considered done (compile, test, checkstyle if applicable).

Do not write any implementation code in this session.
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
