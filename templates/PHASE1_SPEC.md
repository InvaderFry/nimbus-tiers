# PHASE1_SPEC — Phase 1 Planner Specification

This file is the canonical specification for Phase 1 planning output. It is
referenced by:

- The Phase 1 starter prompt in `NIMBUS_GUIDE.md`
- The plan-mode template in `CLAUDE.md`

A Phase 1 session must produce exactly the artifacts listed under `Output`,
following the rules in each subsection. If the user's project inputs
(see `Inputs`) are too sparse to satisfy these rules, ask clarifying
questions before writing any artifact. Do not invent or assume.

---

## Role

You are the Phase 1 planner. You design and verify; you do not implement.

- Do not implement the feature.
- Do not create implementation source files.
- Do not modify implementation source files.
- Do not add dependencies unless explicitly allowed.

## Allowed files

You may create or replace only:

- `CONTEXT.md`
- `PLAN.md`
- `TESTS.md`
- `VERIFY.md`
- `verify.sh`
- `plans/step01.md`, `step02.md`, … one file per implementation step
- `plans/halt-step01.md`, `halt-step02.md`, … created only by the executor
  in Phase 2 if it halts on that step due to a missing artifact

You must not:

- Create implementation source files (Phase 2 owns that).
- Create `CompletedSteps.md` (`phase2.sh` owns it).
- Mark any implementation step DONE.
- Modify `CONTEXT.md` during implementation steps unless explicitly instructed.
- Create files outside the allowed list.

## Inputs

The user provides these inputs in the Phase 1 starter prompt. If any input
is missing, ambiguous, or insufficient to plan against, ask the user before
writing any artifact.

- **FEATURE** — what is being built.
- **TECH STACK** — language, framework, build/test tools, runtime versions.
- **PROJECT STATE** — what exists today; whether the project has been
  scaffolded; which files are boilerplate vs. project-specific.
- **OUTPUT / BEHAVIOR CONTRACT** — the observable behavior that proves the
  feature works. Whichever of the following apply should be specified:
  HTTP endpoints (method, path, request/response shape, status codes);
  CLI commands (arguments, flags, stdout/stderr format, exit codes);
  files produced (paths, formats, encoding, size constraints);
  logs (lines emitted, level, format);
  side effects (database writes, queue messages, external calls);
  error conditions (trigger inputs, error output).
  If none of those categories applies, the user should describe the
  observable outcome that would prove the feature works to an outside
  observer.
- **EXTERNAL DEPENDENCIES** — APIs, databases, files, network, credentials.
  Which of these must be mocked in automated tests.

## Execution model (constraints downstream phases impose on Phase 1)

- `PLAN.md` and `TESTS.md` are for humans and Phase 3 review only.
- The Phase 2 executor reads only `CONTEXT.md` and one `plans/stepNN.md`
  file at a time. It does not read `PLAN.md` or `TESTS.md`.
- Therefore every `plans/stepNN.md` file must be self-contained.
- Step files must not assume earlier steps were completed exactly as planned.
- Every step must tell the executor to inspect real current files before
  editing.
- If the executor halts mid-step due to a missing artifact, it writes
  `plans/halt-stepNN.md` and stops. `phase2.sh` will exit non-zero and the
  next run will not proceed automatically; a human or orchestrator reviews
  the halt report before the next step begins.

---

## Output

### 0. CONTEXT.md

A concise project context document the executor reads alongside every step
file.

Include:

- Project name and one-sentence purpose.
- One or two sentences describing the feature so the executor understands
  the broader goal without needing to read `PLAN.md`. Do not include the
  step-by-step plan.
- Tech stack (language, framework, build tool, key versions).
- Project structure overview (key directories and their roles).
- Build and test commands.
- Invariants every step must respect (coding conventions, file naming, env
  vars, security constraints, etc.).

Do not include the step-by-step plan or test strategy. Keep `CONTEXT.md`
under 350 words. It is a stable reference, not a changelog. It must not be
modified during implementation steps unless explicitly instructed.

### 1. PLAN.md

A numbered implementation plan.

Each step must:

- Be independently dispatchable to a small AI coding agent.
- Fit within the per-step token cap (see §5).
- Have a clear done condition.
- Include setup/project-structure work if needed.
- Include testing work where appropriate.
- Include final manual or end-to-end verification if needed.

Avoid steps whose only work is creating a single empty file or adding one
import. Combine trivial actions into a meaningful step.

Do not include implementation code. Do not mark any step DONE.

### 2. TESTS.md

The acceptance test strategy.

Include:

- Automated checks.
- Manual checks (in a separate section).
- Success-path coverage.
- Edge-case coverage.
- Output formatting coverage.
- Side-effect coverage.
- Error-handling coverage.
- Mocking strategy for external dependencies.
- Notes on avoiding live network in automated tests unless explicitly
  required.

Do not include actual test source code.

### 3. VERIFY.md

Project-specific verification instructions.

Use these sections:

- Required before Phase 2 begins
- Required before every AI step commit
- Required before merge / final review
- Human review required

Verification policy:

- The "Required before Phase 2 begins" section must include:
    1. Run `./verify.sh` and confirm it exits 0 when the project is
       uninitialized (sentinel file absent).
    2. Introduce a deliberate test failure, run `./verify.sh`, confirm it
       exits non-zero and surfaces the failure clearly. Then revert the
       deliberate failure. If introducing a test failure is not feasible,
       confirm at minimum that the uninitialized case exits 0 cleanly.
- Before every AI step commit, the single command must be: `./verify.sh`.
- A step may only be marked DONE after `./verify.sh` exits 0.
- Do not commit if `./verify.sh` fails.
- Manual checks and live-network checks belong in final review, not in
  per-step checks.
- Per-step checks must be automated, deterministic, and local unless
  explicitly required.
- Mention runtime/build versions.
- Mention generated artifacts that must not be committed.
- Mention sensitive output (secrets, tokens, PII) that must be sanitized.
- The "Required before merge / final review" section must include a check
  that `CONTEXT.md` still accurately describes the project structure, build
  commands, and feature summary as built — not just as originally planned.
  If it has drifted, update it before merging.

### 4. verify.sh

A Bash script that:

- Starts with `set -euo pipefail`.
- Can be run safely from the project root.
- Detects whether the project is initialized using a stack-specific
  sentinel file derived from TECH STACK:

    | Stack  | Sentinel                                                        |
    |--------|-----------------------------------------------------------------|
    | Maven  | `pom.xml`                                                       |
    | Gradle | `build.gradle` or `build.gradle.kts`                            |
    | Node   | `package.json`                                                  |
    | Go     | `go.mod`                                                        |
    | Rust   | `Cargo.toml`                                                    |
    | Python | `pyproject.toml` first; else `requirements.txt`; if neither, print a message naming both and exit 0 |
    | Ruby   | `Gemfile`                                                       |

  Use whichever sentinel is appropriate for this project. If the expected
  sentinel does not exist, print a message that names it and exit 0.
- If initialized, runs the automated build/lint/test gate.
- Does not perform manual checks.
- Does not perform live-network checks unless explicitly required.
- Keeps logs concise and focused on failures.
- Is executable.

Quiet-log discipline (any noisy toolchain — Maven, Gradle, npm, pytest,
go test, cargo, etc.):

- Prefer quiet, batch, or CI mode when available.
- Suppress routine banners and debug logs when safe.
- Preserve failure summaries, error lines, stack traces, and test failure
  messages.
- Do not hide the final exit status.
- Do not make failures look successful.
- If using a pipeline to filter logs, set `set -o pipefail` and avoid
  swallowing exit codes.

A ready-to-paste stack-specific helper for this project lives in
`PHASE1_VERIFY_HELPER.md` at the project root (selected at scaffold time
based on this project's stack). Inline that snippet — do not invent your
own quiet-log filter, and do not adapt a helper for a different stack.

### 5. plans/stepNN.md

One file per `PLAN.md` step. Use zero-padded two-digit numbers
(`step01.md`, `step02.md`, … `step10.md`, `step11.md`, …).

**Token cap: each step file must not exceed 400 tokens (~300 words).** If a
step cannot be expressed within that limit, split it into two steps in
`PLAN.md`. `phase2.sh` warns when a step file exceeds ~320 words.

Omit any section that does not apply to this step rather than writing a
placeholder. Every section that is present must contain substantive content.

Required structure:

```
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
```

Additional guardrails for all step files:

- Do not assume previous steps were completed exactly as planned.
- Provide fallback guidance when state is uncertain.
- Do not say "use X, not Y" for version-sensitive APIs without explaining
  how to verify X is available.
- For any new file, class, module, route, handler, command, or piece of
  functionality, instruct the executor to check for duplicates first.
- If a required artifact from a prior step is absent, write the gap to
  `plans/halt-stepNN.md` and stop — do not work around it or create a
  substitute.

---

## Worked example: a well-formed step file

This is what a `plans/step03.md` looks like in practice. It is roughly
260 words — well under the 400-token cap.

```
# Step 03: Add weather fetch service

## Goal
Add a service that fetches current weather for Plano, TX from a
keyless public API and returns a typed reading.

## Inspect first
- Check src/main/java/com/example/weather/ exists. If not, the
  package layout has not been created — write the gap to
  plans/halt-step03.md and stop.
- Check whether a WeatherService already exists in that package. If
  yes, update it; do not create a duplicate.
- Confirm pom.xml declares spring-web. If not, halt.

## Files to change
- src/main/java/com/example/weather/WeatherService.java (create if missing)
- src/main/java/com/example/weather/WeatherReading.java (create if missing)

## Work
- WeatherReading is an immutable record: temperatureF (double),
  condition (String), humidityPct (int), windMph (double),
  observedAt (Instant).
- WeatherService exposes WeatherReading fetch() that calls the
  open-meteo current-weather endpoint for Plano (33.0198, -96.6989),
  parses the response, and returns a populated WeatherReading.
- On non-2xx response or parse failure, throw a checked
  WeatherFetchException with the underlying cause.
- Use Spring's RestClient (Spring Boot 3.2+). Verify RestClient is
  available before using it; do not fall back to the deprecated
  RestTemplate.

## Edge cases
- Response missing optional fields: throw WeatherFetchException; do
  not return partial data.
- Network timeout: configure 5-second connect/read timeouts.

## Acceptance tests
- Mock RestClient to return a known JSON payload; assert all five
  fields parse correctly.
- Mock a 503 response; assert WeatherFetchException is thrown.
- Mock a payload with humidity missing; assert WeatherFetchException
  is thrown.

## Done condition
- WeatherService and WeatherReading exist with the behavior above.
- All three acceptance tests pass.
- ./verify.sh exits 0.
```
