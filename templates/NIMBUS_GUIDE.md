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
We are in Phase 1: planning and verification design only.

Do not write implementation code or source files.
Only create or replace:
- PLAN.md
- TESTS.md
- VERIFY.md
- verify.sh

FEATURE:
[Describe feature.]

TECH STACK:
[Language, framework, build/test tools, required versions.]

PROJECT STATE:
[Describe what exists and what is missing.]

OUTPUT / BEHAVIOR CONTRACT:
[Describe exact expected behavior, outputs, files, API responses, logs, exit codes, etc.]

EXTERNAL DEPENDENCIES:
[APIs, databases, files, network, credentials, etc. Say what must be mocked in automated tests.]

Create:

1. PLAN.md
- Numbered implementation steps.
- Each step small enough for an AI coding agent to do independently.
- Each step has a clear done condition.
- Include setup/project-structure steps if needed.
- Include testing steps.
- Include final manual/end-to-end verification if needed.
- No implementation code.

2. TESTS.md
- Automated acceptance test strategy.
- Tests must be deterministic and avoid live network unless explicitly required.
- Cover success path, edge cases, output formatting, side effects, and error handling.
- Separate manual checks from automated checks.
- No actual test source code.

3. VERIFY.md
- Project-specific verification instructions.
- Clearly separate:
  - Required before every AI step commit
  - Required before merge / final review
  - Human review required
- Before every AI step commit, the single command must be: ./verify.sh
- A step may only be marked DONE after ./verify.sh exits 0.
- Do not commit if ./verify.sh fails.
- Manual/network checks should be final-review checks, not required after every small step unless specifically relevant.
- Mention runtime/build versions, generated artifacts not to commit, and sensitive output/logs to sanitize.

4. verify.sh
- Bash script with set -euo pipefail.
- Safe to run from project root.
- If the project is not initialized yet, print a clear message and exit 0.
- Once initialized, run the project’s automated build/lint/test gate.
- Do not run manual/live-network checks unless explicitly required.
- Make executable if possible.

IMPORTANT:
Do not create implementation source files.
Do not add dependencies unless explicitly allowed.
Do not create CompletedSteps.md.
Do not mark any implementation step DONE.
```

#### Example

```
We are in Phase 1: planning and verification design only.

Do not write implementation code or source files.
Only create or replace:
- PLAN.md
- TESTS.md
- VERIFY.md
- verify.sh

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
.aider.conf.yml, etc.). There is no src/ directory, no pom.xml, and no
Java source. The plan must include a step to create the Spring Boot
project structure from scratch.

All content in CONTEXT.md, VERIFY.md, and CLAUDE.md is boilerplate from
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

Create:

1. PLAN.md
- Numbered implementation steps.
- Each step small enough for an AI coding agent to do independently.
- Each step has a clear done condition.
- Include setup/project-structure steps if needed.
- Include testing steps.
- Include final manual/end-to-end verification if needed.
- No implementation code.

2. TESTS.md
- Automated acceptance test strategy.
- Tests must be deterministic and avoid live network unless explicitly required.
- Cover success path, edge cases, output formatting, side effects, and error handling.
- Separate manual checks from automated checks.
- No actual test source code.

3. VERIFY.md
- Project-specific verification instructions.
- Clearly separate:
  - Required before every AI step commit
  - Required before merge / final review
  - Human review required
- Before every AI step commit, the single command must be: ./verify.sh
- A step may only be marked DONE after ./verify.sh exits 0.
- Do not commit if ./verify.sh fails.
- Manual/network checks should be final-review checks, not required after every small step unless specifically relevant.
- Mention runtime/build versions, generated artifacts not to commit, and sensitive output/logs to sanitize.

4. verify.sh
- Bash script with set -euo pipefail.
- Safe to run from project root.
- If the project is not initialized yet, print a clear message and exit 0.
- Once initialized, run the project’s automated build/lint/test gate.
- Do not run manual/live-network checks unless explicitly required.
- Make executable if possible.

IMPORTANT:
Do not create implementation source files.
Do not add dependencies unless explicitly allowed.
Do not create CompletedSteps.md.
Do not mark any implementation step DONE.
```

### Phase 2 starter prompt

Paste this at the Aider `>` prompt after startup.

```
Execute the plan in PLAN.md step by step, starting with step 1.
Before editing any file, add it to the chat with /add <path>.
Make one commit per step using the step number as the commit message prefix (e.g. "Step 1: ...").
Do not skip steps or combine them.
```

#### Example: one step at a time (recommended)

Instead of pasting a prompt interactively, run Aider non-interactively once per step. Re-run the same command until all steps are done — it picks up where it left off each time via `CompletedSteps.md`.

```bash
aider \
  --read PLAN.md \
  --read TESTS.md \
  --read CONTEXT.md \
  --read VERIFY.md \
  CompletedSteps.md \
  --yes \
  -m "Read CompletedSteps.md to find the first step not listed as DONE. \
If CompletedSteps.md does not exist, create it with the header '# Completed Steps'. \
Implement exactly that one step from PLAN.md — no more. \
Do not refactor unrelated code, do not implement later steps, and do not change behavior outside the current step unless required. \
Use TESTS.md and VERIFY.md to determine how to verify the change. \
If verification instructions are missing or ambiguous, stop without marking the step done. \
Only mark the step done after tests pass. \
Append a line to CompletedSteps.md in this exact format: 'Step N: DONE — <one-line summary>'. \
Then commit all changed files with the message 'Step N: <one-line summary>'."
```

- `CompletedSteps.md` is passed as an editable file (not `--read`) so Aider can write to it.
- `--yes` auto-confirms file prompts so the run never hangs waiting for input.
- Tests must pass before the step is marked done.
- Each run produces exactly one commit; re-run until all steps show DONE.

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
