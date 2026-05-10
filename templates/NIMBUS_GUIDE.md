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

Do not write implementation code or source files.
Only create or replace:
- PLAN.md
- TESTS.md
- VERIFY.md
- verify.sh
- plans/step01.md, step02.md, ... (one per step)

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

5. plans/step01.md, step02.md, ... (one file per PLAN.md step)
- Each file covers exactly one step: file(s) to change, what to do, edge cases, and acceptance tests for that step only.
- Must be self-contained — the executor reads only this file plus CONTEXT.md.
- Keep each file under ~400 tokens (roughly 300 words). The local model has a 10K token context window.
- Number files with zero-padded two digits: step01.md, step02.md, ..., step10.md, etc.
- PLAN.md and TESTS.md are for humans and Phase 3 review — the executor never reads them.

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
- plans/step01.md, step02.md, ... (one per step)

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
Java source or it will be barebones. The plan must include a step to create the Spring Boot
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

5. plans/step01.md, step02.md, ... (one file per PLAN.md step)
- Each file covers exactly one step: file(s) to change, what to do, edge cases, and acceptance tests for that step only.
- Must be self-contained — the executor reads only this file plus CONTEXT.md.
- Keep each file under ~400 tokens (roughly 300 words). The local model has a 10K token context window.
- Number files with zero-padded two digits: step01.md, step02.md, ..., step10.md, etc.
- PLAN.md and TESTS.md are for humans and Phase 3 review — the executor never reads them.

IMPORTANT:
Do not create implementation source files.
Do not add dependencies unless explicitly allowed.
Do not create CompletedSteps.md.
Do not mark any implementation step DONE.
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
