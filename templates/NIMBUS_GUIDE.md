# {{PROJECT_NAME}}

Scaffolded from the [nimbus-tiers](https://github.com/invaderfry/nimbus-tiers) template. This project follows the **Hybrid AI Coding Architecture** — a three-phase Plan → Execute → Review flow that routes work across local models, free cloud APIs, and frontier subscriptions.

## The flow

| Phase | Tool | Output |
|---|---|---|
| 1. Plan | Claude Code (frontier) | `PLAN.md`, `TESTS.md`, `plans/step01.md` … `stepNN.md`, updated `CONTEXT.md` |
| 2. Execute | Aider + local Qwen3-32B (TabbyAPI) | Series of git commits, one per step |
| 3. Review | Claude Code (frontier) | Fix list or `APPROVED` |

See [`docs/architecture.md`](./docs/architecture.md) for the full reference.

## Per-feature workflow

```bash
# Phase 1 — plan in Claude Code
claude            # paste the Phase 1 starter prompt below, then iterate

# Phase 2 — execute steps one at a time
./phase2.sh   # re-run until all steps show DONE

# Phase 3 — find the base commit, then open Claude Code
git log --oneline   # copy the hash of the last commit before execution started
claude              # paste the Phase 3 starter prompt below, filling in that hash

# Final gate — run VERIFY.md before merge
```

### Phase 1 starter prompt

Copy this as your **first message** when opening a new Claude Code session for planning. Fill in the bracketed parts.

```
We are in Phase 1: planning and verification design only.

Do not implement the feature.

Allowed files to create or replace:
- CONTEXT.md
- PLAN.md
- TESTS.md
- VERIFY.md
- verify.sh
- plans/step01.md, step02.md, ... one file per implementation step
- plans/halt-step01.md, halt-step02.md, ... created only if the executor
  halts on that step due to a missing artifact

Do not create implementation source files.
Do not modify implementation source files.
Do not add dependencies unless explicitly allowed.
Do not create CompletedSteps.md.
Do not mark implementation steps DONE.
Do not modify CONTEXT.md during implementation steps unless explicitly instructed.
Do not create files outside the allowed list.

Project inputs:

FEATURE:
[Describe feature.]

TECH STACK:
[Language, framework, build/test tools, required versions.]

PROJECT STATE:
[Describe what exists and what is missing.]

OUTPUT / BEHAVIOR CONTRACT:
Describe the exact expected behavior. Include as many of the following as apply:
- HTTP endpoints: method, path, request shape, response shape, status codes.
- CLI commands: arguments, flags, stdout format, stderr format, exit codes.
- Files produced: paths, formats, encoding, size constraints.
- Logs: which lines are emitted, at what level, in what format.
- Events or side effects: database writes, queue messages, external calls.
- Error conditions: what input triggers an error, what the error output looks like.
If none of these categories applies, describe the observable outcome that
would prove the feature works correctly to an outside observer.

EXTERNAL DEPENDENCIES:
[APIs, databases, files, network, credentials, etc. Say what must be mocked
in automated tests.]

Important execution model:
- PLAN.md and TESTS.md are for humans and Phase 3 review.
- The implementation executor does not read PLAN.md or TESTS.md.
- The implementation executor reads only:
  - CONTEXT.md
  - one plans/stepNN.md file
- Therefore, every plans/stepNN.md file must be self-contained.
- Step files must not assume earlier steps were completed exactly as planned.
- Every step must tell the executor to inspect real current files before editing.
- If the executor halts mid-step due to a missing artifact, a human or
  orchestrator must review the halt report before the next step begins.

Create the following.

0. CONTEXT.md

Write a concise project context document that the implementation executor
will read alongside every step file.

Include:
- Project name and one-sentence purpose.
- One or two sentences describing the feature being built, so the executor
  understands the broader goal without needing to read PLAN.md. Do not
  include the step-by-step plan.
- Tech stack (language, framework, build tool, key versions).
- Project structure overview (key directories and their roles).
- Build and test commands.
- Invariants every step must respect (coding conventions, file naming rules,
  required environment variables, security constraints, etc.).

Do not include the step-by-step plan or test strategy. CONTEXT.md is a
stable reference, not a changelog. Keep it under 350 words. It must not be
modified during implementation steps unless explicitly instructed.

1. PLAN.md

Write a numbered implementation plan.

Each step must:
- Be independently dispatchable to an AI coding agent.
- Be small enough to fit within the step file token limit (see section 5).
- Have a clear done condition.
- Include setup/project-structure work if needed.
- Include testing work where appropriate.
- Include final manual or end-to-end verification if needed.

Avoid steps whose only work is creating a single empty file or adding a
single import. Combine trivial actions into a meaningful step.

Do not include implementation code.
Do not mark any step DONE.

2. TESTS.md

Write the acceptance test strategy.

Include:
- Automated checks.
- Manual checks in a separate section.
- Success path coverage.
- Edge case coverage.
- Output formatting coverage.
- Side effect coverage.
- Error handling coverage.
- Mocking strategy for external dependencies.
- Notes on avoiding live network in automated tests unless explicitly required.

Do not include actual test source code.

3. VERIFY.md

Write project-specific verification instructions.

Use these sections:
- Required before Phase 2 begins
- Required before every AI step commit
- Required before merge / final review
- Human review required

Verification policy:
- The "Required before Phase 2 begins" section must include:
    1. Run ./verify.sh and confirm it exits 0 when the project is
       uninitialized (i.e., the sentinel file is absent).
    2. Introduce a deliberate test failure, run ./verify.sh, and confirm
       it exits non-zero and surfaces the failure clearly. Then revert the
       deliberate failure. If introducing a test failure is not feasible,
       confirm at minimum that the uninitialized case exits 0 cleanly.
- Before every AI step commit, the single command must be: ./verify.sh
- A step may only be marked DONE after ./verify.sh exits 0.
- Do not commit if ./verify.sh fails.
- Manual checks and live-network checks should be final-review checks,
  not per-step checks.
- Per-step checks must be automated, deterministic, and local unless
  explicitly required.
- Mention runtime/build versions.
- Mention generated artifacts that must not be committed.
- Mention sensitive output (secrets, tokens, PII) that must be sanitized.
- In the "Required before merge / final review" section, include a check
  that CONTEXT.md still accurately describes the project structure, build
  commands, and feature summary as built — not just as originally planned.
  If it has drifted, update it before merging.

4. verify.sh

Write a Bash script that:
- Starts with set -euo pipefail.
- Can be run safely from the project root.
- Detects whether the project is initialized using a stack-specific sentinel
  file derived from TECH STACK. Common sentinel files by stack:
    Maven:  pom.xml
    Node:   package.json
    Go:     go.mod
    Rust:   Cargo.toml
    Python: check for pyproject.toml first; if absent, check requirements.txt;
            if neither exists, print a message naming both and exit 0
    Ruby:   Gemfile
  Use whichever sentinel is appropriate for this project. If the expected
  sentinel does not exist, print a message that names it and exit 0.
- If initialized, runs the automated build/lint/test gate.
- Does not perform manual checks.
- Does not perform live-network checks unless explicitly required.
- Keeps logs concise and focused on failures.

For noisy tools (Maven, Gradle, npm, pytest, go test, cargo, etc.):
- Prefer quiet, batch, or CI mode when available.
- Suppress routine banners and debug logs when safe.
- Preserve failure summaries, error lines, stack traces, and test failure
  messages.
- Do not hide the final exit status.
- Do not make failures look successful.
- If using a pipeline to filter logs, use set -o pipefail and avoid
  swallowing exit codes.

If the project uses Maven/Spring, a quiet failure-focused helper may look
like this:

  run_tests_quiet() {
    ./mvnw --batch-mode test \
      -Dspring.main.banner-mode=off \
      -Dlogging.level.root=ERROR \
      -Dlogging.level.org.springframework=ERROR \
      -Ddebug=false \
      -Dspring.test.context.failure.threshold=1 \
      -DtrimStackTrace=true \
      2>&1 | awk '
        /APPLICATION FAILED TO START/ {show=1; count=0}
        show && count < 35 {print; count++}
        /\[ERROR\]/ {print}
        /Caused by:/ {print}
        /No qualifying bean/ {print}
        /BUILD FAILURE/ {print}
      '
  }

Use this helper only when the project uses Maven/Spring. For all other
toolchains, apply the same quiet-log principle using tools native to that
stack — do not copy the Maven helper verbatim.

Make verify.sh executable.

5. plans/stepNN.md

Create one file per PLAN.md step:
- plans/step01.md
- plans/step02.md
- plans/step03.md
- Continue using zero-padded two-digit numbers (step10.md, step11.md, ...).

Each file must not exceed 400 tokens (roughly 300 words). If a step cannot
be expressed within this limit, split it into two steps in PLAN.md.

Omit any section that does not apply to this step rather than writing a
placeholder. Every section that is present must contain substantive content.

Each step file must use this structure:

  # Step NN: [Short title]

  ## Goal
  [One-sentence goal.]

  ## Inspect first
  - Inspect actual current files before editing anything.
  - List likely files or directories to check. Do not assume they exist.
  - If this step modifies files that other steps also modify, read the
    current file state before editing — do not assume a prior step's
    output is present.
  - If this step depends on an artifact from an earlier step (a class,
    module, route, file, etc.), verify it exists before proceeding. If it
    is missing, write the gap description to plans/halt-stepNN.md (where
    NN matches this step's number), then stop and take no further action
    in this step. Do not create a substitute or approximation.

  ## Files to change
  - List intended files.
  - Create only if missing; otherwise update existing files carefully.

  ## Work
  - Describe behavior to implement.
  - Prefer behavioral requirements over code samples.
  - Do not include full source code unless absolutely necessary.
  - Include version-compatibility checks for APIs, imports, annotations,
    plugins, or dependencies before using them.

  ## Edge cases
  [Omit if none apply to this step.]

  ## Acceptance tests
  - List behavior-based tests for this step only.
  - Tests must be deterministic.
  - Tests must avoid live network unless explicitly required.
  - Tests must verify behavior, not only compilation.

  ## Done condition
  - State the clear completion condition.
  - ./verify.sh must exit 0 before this step can be marked DONE.

Additional guardrails for all step files:
- Do not assume previous steps were completed exactly as planned.
- Provide fallback guidance when state is uncertain.
- Do not say "use X, not Y" for version-sensitive APIs without explaining
  how to verify X is available.
- For any new file, class, module, route, handler, command, or piece of
  functionality, instruct the executor to check for duplicates first.
- If a required artifact from a prior step is absent, write the gap to
  plans/halt-stepNN.md and stop — do not work around it or create a substitute.
```

#### Example

```
We are in Phase 1: planning and verification design only.

Do not implement the feature.

Allowed files to create or replace:
- CONTEXT.md
- PLAN.md
- TESTS.md
- VERIFY.md
- verify.sh
- plans/step01.md, step02.md, ... one file per implementation step
- plans/halt-step01.md, halt-step02.md, ... created only if the executor
  halts on that step due to a missing artifact

Do not create implementation source files.
Do not modify implementation source files.
Do not add dependencies unless explicitly allowed.
Do not create CompletedSteps.md.
Do not mark implementation steps DONE.
Do not modify CONTEXT.md during implementation steps unless explicitly instructed.
Do not create files outside the allowed list.

Project inputs:

FEATURE:
Create a Java Spring Boot application that fetches the
current weather for Plano, Texas, prints it to the console, and writes
the same output to weather.txt in the project root directory, overwriting
the file on each execution. The process runs, outputs results, and exits with code 0.

TECH STACK:
- Java 21
- Spring Boot
- Maven (the project uses the Maven wrapper: ./mvnw)

PROJECT STATE:
This is the first generation of this project. The directory contains only
nimbus-tiers scaffolding files (CONTEXT.md, VERIFY.md, CLAUDE.md,
.aider.conf.yml, etc.). There might not be src/ directory, no pom.xml, and no
Java source or it will be barebones. The plan must include a step to create the Spring Boot project structure from scratch. All content in CONTEXT.md, VERIFY.md, and CLAUDE.md is boilerplate from
the project generator. Treat every section as a template to be replaced
with project-specific content.

OUTPUT / BEHAVIOR CONTRACT:
Both the console and weather.txt must show these fields, one per line:
  Temperature:  <value> °F
  Condition:    <description, e.g. "Partly Cloudy">
  Humidity:     <value> %
  Wind Speed:   <value> mph
  Observed At:  <ISO-8601 timestamp>

EXTERNAL DEPENDENCIES:
Pick a free weather API that doesn't need an API key. 

Important execution model:
- PLAN.md and TESTS.md are for humans and Phase 3 review.
- The implementation executor does not read PLAN.md or TESTS.md.
- The implementation executor reads only:
  - CONTEXT.md
  - one plans/stepNN.md file
- Therefore, every plans/stepNN.md file must be self-contained.
- Step files must not assume earlier steps were completed exactly as planned.
- Every step must tell the executor to inspect real current files before editing.
- If the executor halts mid-step due to a missing artifact, a human or
  orchestrator must review the halt report before the next step begins.

Create the following.

0. CONTEXT.md

Write a concise project context document that the implementation executor
will read alongside every step file.

Include:
- Project name and one-sentence purpose.
- One or two sentences describing the feature being built, so the executor
  understands the broader goal without needing to read PLAN.md. Do not
  include the step-by-step plan.
- Tech stack (language, framework, build tool, key versions).
- Project structure overview (key directories and their roles).
- Build and test commands.
- Invariants every step must respect (coding conventions, file naming rules,
  required environment variables, security constraints, etc.).

Do not include the step-by-step plan or test strategy. CONTEXT.md is a
stable reference, not a changelog. Keep it under 350 words. It must not be
modified during implementation steps unless explicitly instructed.

1. PLAN.md

Write a numbered implementation plan.

Each step must:
- Be independently dispatchable to an AI coding agent.
- Be small enough to fit within the step file token limit (see section 5).
- Have a clear done condition.
- Include setup/project-structure work if needed.
- Include testing work where appropriate.
- Include final manual or end-to-end verification if needed.

Avoid steps whose only work is creating a single empty file or adding a
single import. Combine trivial actions into a meaningful step.

Do not include implementation code.
Do not mark any step DONE.

2. TESTS.md

Write the acceptance test strategy.

Include:
- Automated checks.
- Manual checks in a separate section.
- Success path coverage.
- Edge case coverage.
- Output formatting coverage.
- Side effect coverage.
- Error handling coverage.
- Mocking strategy for external dependencies.
- Notes on avoiding live network in automated tests unless explicitly required.

Do not include actual test source code.

3. VERIFY.md

Write project-specific verification instructions.

Use these sections:
- Required before Phase 2 begins
- Required before every AI step commit
- Required before merge / final review
- Human review required

Verification policy:
- The "Required before Phase 2 begins" section must include:
    1. Run ./verify.sh and confirm it exits 0 when the project is
       uninitialized (i.e., the sentinel file is absent).
    2. Introduce a deliberate test failure, run ./verify.sh, and confirm
       it exits non-zero and surfaces the failure clearly. Then revert the
       deliberate failure. If introducing a test failure is not feasible,
       confirm at minimum that the uninitialized case exits 0 cleanly.
- Before every AI step commit, the single command must be: ./verify.sh
- A step may only be marked DONE after ./verify.sh exits 0.
- Do not commit if ./verify.sh fails.
- Manual checks and live-network checks should be final-review checks,
  not per-step checks.
- Per-step checks must be automated, deterministic, and local unless
  explicitly required.
- Mention runtime/build versions.
- Mention generated artifacts that must not be committed.
- Mention sensitive output (secrets, tokens, PII) that must be sanitized.
- In the "Required before merge / final review" section, include a check
  that CONTEXT.md still accurately describes the project structure, build
  commands, and feature summary as built — not just as originally planned.
  If it has drifted, update it before merging.

4. verify.sh

Write a Bash script that:
- Starts with set -euo pipefail.
- Can be run safely from the project root.
- Detects whether the project is initialized using a stack-specific sentinel
  file derived from TECH STACK. Common sentinel files by stack:
    Maven:  pom.xml
    Node:   package.json
    Go:     go.mod
    Rust:   Cargo.toml
    Python: check for pyproject.toml first; if absent, check requirements.txt;
            if neither exists, print a message naming both and exit 0
    Ruby:   Gemfile
  Use whichever sentinel is appropriate for this project. If the expected
  sentinel does not exist, print a message that names it and exit 0.
- If initialized, runs the automated build/lint/test gate.
- Does not perform manual checks.
- Does not perform live-network checks unless explicitly required.
- Keeps logs concise and focused on failures.

For noisy tools (Maven, Gradle, npm, pytest, go test, cargo, etc.):
- Prefer quiet, batch, or CI mode when available.
- Suppress routine banners and debug logs when safe.
- Preserve failure summaries, error lines, stack traces, and test failure
  messages.
- Do not hide the final exit status.
- Do not make failures look successful.
- If using a pipeline to filter logs, use set -o pipefail and avoid
  swallowing exit codes.

If the project uses Maven/Spring, a quiet failure-focused helper may look
like this:

  run_tests_quiet() {
    ./mvnw --batch-mode test \
      -Dspring.main.banner-mode=off \
      -Dlogging.level.root=ERROR \
      -Dlogging.level.org.springframework=ERROR \
      -Ddebug=false \
      -Dspring.test.context.failure.threshold=1 \
      -DtrimStackTrace=true \
      2>&1 | awk '
        /APPLICATION FAILED TO START/ {show=1; count=0}
        show && count < 35 {print; count++}
        /\[ERROR\]/ {print}
        /Caused by:/ {print}
        /No qualifying bean/ {print}
        /BUILD FAILURE/ {print}
      '
  }

Use this helper only when the project uses Maven/Spring. For all other
toolchains, apply the same quiet-log principle using tools native to that
stack — do not copy the Maven helper verbatim.

Make verify.sh executable.

5. plans/stepNN.md

Create one file per PLAN.md step:
- plans/step01.md
- plans/step02.md
- plans/step03.md
- Continue using zero-padded two-digit numbers (step10.md, step11.md, ...).

Each file must not exceed 400 tokens (roughly 300 words). If a step cannot
be expressed within this limit, split it into two steps in PLAN.md.

Omit any section that does not apply to this step rather than writing a
placeholder. Every section that is present must contain substantive content.

Each step file must use this structure:

  # Step NN: [Short title]

  ## Goal
  [One-sentence goal.]

  ## Inspect first
  - Inspect actual current files before editing anything.
  - List likely files or directories to check. Do not assume they exist.
  - If this step modifies files that other steps also modify, read the
    current file state before editing — do not assume a prior step's
    output is present.
  - If this step depends on an artifact from an earlier step (a class,
    module, route, file, etc.), verify it exists before proceeding. If it
    is missing, write the gap description to plans/halt-stepNN.md (where
    NN matches this step's number), then stop and take no further action
    in this step. Do not create a substitute or approximation.

  ## Files to change
  - List intended files.
  - Create only if missing; otherwise update existing files carefully.

  ## Work
  - Describe behavior to implement.
  - Prefer behavioral requirements over code samples.
  - Do not include full source code unless absolutely necessary.
  - Include version-compatibility checks for APIs, imports, annotations,
    plugins, or dependencies before using them.

  ## Edge cases
  [Omit if none apply to this step.]

  ## Acceptance tests
  - List behavior-based tests for this step only.
  - Tests must be deterministic.
  - Tests must avoid live network unless explicitly required.
  - Tests must verify behavior, not only compilation.

  ## Done condition
  - State the clear completion condition.
  - ./verify.sh must exit 0 before this step can be marked DONE.

Additional guardrails for all step files:
- Do not assume previous steps were completed exactly as planned.
- Provide fallback guidance when state is uncertain.
- Do not say "use X, not Y" for version-sensitive APIs without explaining
  how to verify X is available.
- For any new file, class, module, route, handler, command, or piece of
  functionality, instruct the executor to check for duplicates first.
- If a required artifact from a prior step is absent, write the gap to
  plans/halt-stepNN.md and stop — do not work around it or create a substitute.
```

### Phase 2: running the executor

#### Recommended: `./phase2.sh`

Run the wrapper script from your project root. Re-run it until all steps show DONE:

```bash
./phase2.sh
```

What it does each run:

1. Reads `CompletedSteps.md` to find the next step number `N`.
2. Loads `plans/stepNN.md` — only that step, nothing else.
3. Calls Aider; `map-tokens: 0` and `edit-format: diff` are applied automatically from `.aider.conf.yml` to stay within the 10K token context window.
4. Runs `./verify.sh` automatically after each edit attempt (via `--auto-test`).
5. After Aider exits, `phase2.sh` checks Aider's exit code and whether any files were modified. If Aider exited non-zero, or exited 0 with no file changes (e.g. bad API key, unreachable model), the step is not recorded and the script exits 1.
6. If both guards pass, `phase2.sh` re-runs `./verify.sh` itself. On success it appends `Step N: DONE` to `CompletedSteps.md` and commits. Bookkeeping is owned by the shell, not Aider — so a crash in Aider's internal summarization step cannot lose progress.
7. On failure: stops without touching `CompletedSteps.md` or git history.
8. On the final run (no more step files): removes `plans/step*.md`, archives `PLAN.md` to `plans/YYYY-MM-<branch>.md`, and commits both in one go.

Notes:
- `CompletedSteps.md` is written by `phase2.sh` after Aider exits, not by Aider itself. This is intentional — delegating bookkeeping to Aider is fragile because Aider can crash after verification passes but before it finishes its summarization step, leaving the step recorded as incomplete.
- `--yes` auto-confirms file prompts so the run never hangs.
- Each run produces exactly one commit.

#### Alternative: running a step manually

If you want to run a step by hand, open `phase2.sh` — the flags and `-m` prompt in that file are the exact instructions the executor receives. Copy and adapt as needed rather than constructing the command from scratch.

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
| `CONTEXT.md` | Invariants, public contracts, do-not-touch areas (committed, always loaded by Aider). |
| `VERIFY.md` | Repo-level definition of "done" (committed, Phase 3 reference — not loaded by executor). |
| `PLAN.md` | Per-feature human-readable overview (gitignored, Phase 3 reference — not loaded by executor). |
| `TESTS.md` | Per-feature acceptance test checklist (gitignored, Phase 3 reference — not loaded by executor). |
| `plans/step01.md` … | Per-step executor files generated by Phase 1. Each covers one step only. Loaded one at a time by `phase2.sh`. |
| `plans/YYYY-MM-*.md` | Archive of completed feature plans. Archived automatically by `phase2.sh` when all steps complete. |
| `phase2.sh` | Executor wrapper: finds next step, runs Aider, commits on success. |
| `CompletedSteps.md` | Step completion log written by `phase2.sh`. Tracks which steps are DONE. |
| `logs/ai-routing.csv` | Lightweight metrics log of where work was routed. |
| `docs/architecture.md` | Full architecture reference. |
| `.aider.conf.yml` | Aider config (Path C defaults: local TabbyAPI, `map-tokens: 0`, `edit-format: diff`). |
| `.aiderignore` | Files Aider must not read (secrets, env, credentials). |

## Quota budget (rough estimates)

- Plan: ~50K Claude tokens per feature.
- Execute: 0 Claude tokens (all local).
- Review: ~30K Claude tokens.
- Optional fix loop: ~30K.

If you find yourself escalating >30% of execution to cloud, your plans are not specific enough — invest more time in Phase 1.
