# {{PROJECT_NAME}}

Scaffolded from the [nimbus-tiers](https://github.com/invaderfry/nimbus-tiers) template. This project follows the **Hybrid AI Coding Architecture** — a three-phase Plan → Execute → Review flow that routes work across local models, free cloud APIs, and frontier subscriptions.

## The flow

| Phase | Tool | Output |
|---|---|---|
| 1. Plan | Claude Code (frontier) | `PLAN.md`, `TESTS.md`, `plans/step01.md` … `stepNN.md`, updated `CONTEXT.md` |
| 2. Execute | Aider + local Qwen2.5-Coder-14B (TabbyAPI) | Series of git commits, one per step |
| 3. Review | Claude Code (frontier) | Fix list or `APPROVED` |

See [`docs/architecture.md`](./docs/architecture.md) for the full reference. The canonical Phase 1 spec lives in [`PHASE1_SPEC.md`](./PHASE1_SPEC.md).

## Per-feature workflow

Phase 1 artifacts and Phase 2 commits all land on a feature branch; master
stays clean until Phase 3 signs off.

```bash
# Pre-flight — create your feature branch
git checkout master               # start from the clean baseline
git checkout -b feature/<name>    # all phase commits land here

# Phase 1 — plan in Claude Code
claude            # paste the Phase 1 starter prompt below, then iterate

# Phase 2 — execute steps one at a time
./phase2.sh   # re-run until all steps show DONE

# Phase 3 — find the base commit, then open Claude Code
git log --oneline   # copy the hash of the last commit before execution started
claude              # paste the Phase 3 starter prompt below, filling in that hash

# Merge — only after Phase 3 returns APPROVED
git checkout master
git merge --ff-only feature/<name>
```

### Phase 1 starter prompt

Copy this as your **first message** when opening a new Claude Code session for planning. Fill in the bracketed parts. The full output schema, allowed-files list, per-step token cap, halt semantics, and per-section policy live in [`PHASE1_SPEC.md`](./PHASE1_SPEC.md) — Claude must follow it exactly.

```
We are in Phase 1: planning and verification design only.

Read PHASE1_SPEC.md and follow it exactly. It defines the role, allowed
files, output schema, per-step token cap, halt semantics, and per-section
policy. Do not deviate from it.

Do not implement the feature.

If any project input below is missing, ambiguous, or insufficient to plan
against, ask clarifying questions before writing any artifact. Do not
invent or assume.

For verify.sh, inline the snippet from PHASE1_VERIFY_HELPER.md (which is
already specific to this project's stack). Do not invent your own quiet-log
filter for a stack the helper does not cover.

Project inputs:

FEATURE:
[Describe feature.]

TECH STACK:
[Language, framework, build/test tools, required versions.]

PROJECT STATE:
[What exists today. Note whether the project has been scaffolded.]

OUTPUT / BEHAVIOR CONTRACT:
[Observable behavior that proves the feature works. See PHASE1_SPEC.md
§Inputs for which categories typically apply.]

EXTERNAL DEPENDENCIES:
[APIs, databases, files, network, credentials. State what must be mocked
in automated tests.]
```

#### Example (Project inputs only)

The starter prompt above is constant; only the bracketed inputs change per feature. Here is one filled-in `Project inputs` block from a real run:

```
Project inputs:

FEATURE:
Create a Java Spring Boot application that fetches the current weather
for Plano, Texas, prints it to the console, and writes the same output
to weather.txt in the project root directory, overwriting the file on
each execution. The process runs, outputs results, and exits with code 0.

TECH STACK:
- Java 21
- Spring Boot
- Maven (the project uses the Maven wrapper: ./mvnw)

PROJECT STATE:
This is the first generation of this project. The directory contains only
nimbus-tiers scaffolding files (CONTEXT.md, VERIFY.md, CLAUDE.md,
.aider.conf.yml, etc.). There might not be a src/ directory, no pom.xml,
and no Java source — or it will be barebones. The plan must include a
step to create the Spring Boot project structure from scratch. All
content in CONTEXT.md, VERIFY.md, and CLAUDE.md is boilerplate from the
project generator. Treat every section as a template to be replaced with
project-specific content.

OUTPUT / BEHAVIOR CONTRACT:
Both the console and weather.txt must show these fields, one per line:
  Temperature:  <value> °F
  Condition:    <description, e.g. "Partly Cloudy">
  Humidity:     <value> %
  Wind Speed:   <value> mph
  Observed At:  <ISO-8601 timestamp>

EXTERNAL DEPENDENCIES:
Pick a free weather API that doesn't need an API key.
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
3. Warns if the step file exceeds ~320 words (the planner is supposed to keep step files under 400 tokens / ~300 words; warning surfaces drift before it bites Aider's context).
4. Calls Aider; `map-tokens: 0` and `edit-format: diff` are applied automatically from `.aider.conf.yml` to stay within the 10K token context window. **Exception:** `phase2.sh` overrides the edit format to `--edit-format whole` when every file listed in `## Files to change` is whole-safe — i.e. each target is either brand-new (no file on disk yet) or an existing file at or under the whole-file threshold (~120 lines, override via `PHASE2_WHOLE_FILE_MAX_LINES`). Whole-file format is far more reliable for local models than the SEARCH/REPLACE protocol small models get wrong. A single oversized existing target forces the step back to `diff` (reproducing a large file in full risks truncation and loops); for those, give the executor verbatim anchors in the step file. Aider runs under a 15-minute wall-clock timeout (bounded blast radius if the model gets stuck). Note: `--max-reflections` is not passed — it is not exposed by the installed Aider version.
5. Runs `./verify.sh` after Aider exits. `phase2.sh` invokes it directly (`--no-auto-test` is passed to Aider so Aider itself never calls the test runner).
6. After Aider exits, `phase2.sh` checks Aider's exit code and whether any files were modified. If Aider exited non-zero, or exited 0 with no file changes (e.g. bad API key, unreachable model), the step is not recorded and the script exits 1.
7. **Single-run lock.** `phase2.sh` acquires `.git/phase2.lock` at startup and exits early if another run is already active. This avoids concurrent execution races around sentinels and step bookkeeping.
   - Lock ownership is tracked with both PID and proc start time to avoid PID-reuse false positives.
   - If the lock owner is no longer alive (for example, after a host crash or `SIGKILL`) or PID/start-time no longer match, `phase2.sh` auto-recovers the stale lock and continues.
8. **Halt detection.** If the only file the executor modified is `plans/halt-stepNN.md`, the step was halted intentionally because a required prior artifact was missing. `phase2.sh` exits **2** with a clear message and does not record the step. Review the halt report, fix the upstream gap, then re-run.
9. If both guards pass, `phase2.sh` re-runs `./verify.sh` itself. On success it appends `Step N: DONE` to `CompletedSteps.md`, commits, and appends one row to `logs/ai-routing.csv` (date, repo, step, tier, outcome, approximate diff line count). Bookkeeping is owned by the shell, not Aider — so a crash in Aider's internal summarization step cannot lose progress.
10. On failure: stops without touching `CompletedSteps.md` or git history.
11. On the final run (no more step files): removes `plans/step*.md`, archives `PLAN.md` to `plans/YYYY-MM-<branch>.md`, and commits both in one go.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Step recorded DONE, or all steps complete |
| 1 | Aider failure, empty diff, or `verify.sh` failed — step not recorded |
| 2 | Step halted intentionally (`plans/halt-stepNN.md` written) — review the halt report |

Notes:

- **Each Aider invocation runs under a 15-minute wall-clock timeout.** A step that hits it is killed (hard-kill 30s later if needed) and NOT recorded — re-run after fixing the cause; a step that legitimately needs 15 minutes of generation is doing too much and should be split.
- **Preflight enforces a minimum served context window.** When the executor is a local TabbyAPI server, `phase2.sh` reads `max_seq_len` from `/v1/model` and aborts if it is below 16384 — a starved context window truncates Aider's prompt mid-file and is the root cause of most degenerate-loop and SEARCH/REPLACE failures. Override the floor with `PHASE2_MIN_CTX=<n>` (or `0` to disable). Recommended server settings live in `docs/tabbyapi-nimbus-example.yml`.
- **Preflight reconciles the configured model against what the server actually serves.** Under TabbyAPI single-model mode the `model:` in `.aider.conf.yml` is a label, not a selector — the server runs whatever weights are loaded, so a mismatch (e.g. an `exl2` quant loaded while the config names `exl3-6.0bpw`) means every step runs on a different model than the logs claim. By default the mismatch is a per-run WARN (server id formatting varies); set `PHASE2_STRICT_MODEL_MATCH=1` to make it abort instead. Do not run a feature's steps under a sustained mismatch — fix the server's loaded model or the config label first.
- `CompletedSteps.md` is committed by `phase2.sh` on every successful step (it is not gitignored). This keeps branch state self-describing.
- `CompletedSteps.md` is written by `phase2.sh` after Aider exits, not by Aider itself. This is intentional — delegating bookkeeping to Aider is fragile because Aider can crash after verification passes but before it finishes its summarization step, leaving the step recorded as incomplete.
- `--yes` auto-confirms file prompts so the run never hangs.
- Each successful run produces exactly one commit.

#### What to expect from the local executor, by stack

- **Python / Node:** most steps succeed locally on a well-served 14B
  (32K context, Q8 KV cache — see `docs/tabbyapi-nimbus-example.yml`).
- **Java Spring Boot (Maven/Gradle):** the hardest workload for a 14B-class
  model — each step's output is 3–5× more verbose than the Python equivalent,
  and the framework has known traps (HTTP-client mixing, `@SpringBootTest` vs
  test slices, package-path bugs; `PHASE1_SPEC.md` carries guardrails for
  each). Expect a meaningful fraction of steps to need escalation: set
  `PHASE2_FALLBACK_MODEL` (below) so failed steps retry on Groq automatically.
  Escalations on Java are normal operation, not a sign the pipeline is broken —
  but the >30% rule at the end of this section still applies: above that,
  invest in more specific step files, not a bigger model.

#### When a step keeps failing

**Automatic fallback (recommended):** export `PHASE2_FALLBACK_MODEL` (and the
matching API key) and `phase2.sh` escalates by itself — after a step fails once
on the local model, the next run re-invokes Aider with the fallback model and
logs the run as tier 2 (`escalated_from=local`) in `logs/ai-routing.csv`:

```bash
export GROQ_API_KEY=gsk_...
export PHASE2_FALLBACK_MODEL=groq/llama-3.3-70b-versatile
./phase2.sh   # first failure stays local; the retry runs on Groq
```

If `phase2.sh` exits 1 on the same step twice in a row, do not just keep retrying — the step is likely underspecified or has a missing upstream artifact. Use this fallback ladder:

1. **Read `plans/stepNN.log`** (and the auto-incremented `stepNN-2.log`, `stepNN-3.log`, …). Look for the actual failure: a verify.sh diagnostic, a missing import, a wrong API.
2. **If the step depends on something that doesn't exist yet**, write a halt report yourself (`plans/halt-stepNN.md`) describing the gap, then go back to Phase 1 and add or reorder steps. Do not paper over the gap by hand-editing source.
3. **If the step file is too vague or too large**, return to Phase 1 and rewrite or split it. The 400-token cap exists for a reason; if you're hitting it, the step is doing too much.
4. **If two consecutive rewrites still fail**, escalate to Phase 3 / frontier review for a single targeted commit, then resume Phase 2 on the next step.

Java note (Maven and Gradle): the scaffolded project automatically includes
`src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker` with
`mock-maker-subclass`. This prevents Mockito/Byte Buddy self-attach failures
in WSL/containers. If the error still appears, verify the file was copied
correctly and that your tests do not explicitly require inline mocking.

Upgrade note (interrupted-run detection): older versions of `phase2.sh` used a
dirty-tree heuristic to detect an interrupted prior run. The current version
uses an explicit sentinel file at `.git/phase2-wip-stepNN` instead. If you are
upgrading mid-feature and the new `phase2.sh` refuses to start because the tree
is dirty, commit/stash/discard the unrelated changes and re-run. If your tree
is dirty *because* a prior run was interrupted, recreate the sentinel manually
for the next step (e.g. for step 3: `touch .git/phase2-wip-step03`), then
re-run — `phase2.sh` will pre-flight verify and skip Aider if the step is
already complete.

Aider config note: `phase2.sh` reads `model`, `openai-api-key`, and
`openai-api-base` from `.aider.conf.yml` for its preflight reachability check.
It is a `grep`/`sed` reader, not a YAML parser — only top-level
`key: value` lines (with optional `"`/`'` quoting) are recognized. Aider
itself parses the full YAML, so any value it accepts will still work at
runtime; only the preflight check may skip checking it.

If you find yourself escalating >30% of execution to cloud, the plans are not specific enough — invest more time in Phase 1.

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
| `PHASE1_SPEC.md` | Canonical Phase 1 planner spec (committed). The source of truth for what Phase 1 must produce. |
| `PLAN.md` | Per-feature human-readable overview (gitignored, Phase 3 reference — not loaded by executor). |
| `TESTS.md` | Per-feature acceptance test checklist (gitignored, Phase 3 reference — not loaded by executor). |
| `plans/step01.md` … | Per-step executor files generated by Phase 1. Each covers one step only. Loaded one at a time by `phase2.sh`. |
| `plans/halt-stepNN.md` | Written by the Phase 2 executor when a required prior artifact is missing. Triggers exit code 2 from `phase2.sh`. |
| `plans/YYYY-MM-*.md` | Archive of completed feature plans. Archived automatically by `phase2.sh` when all steps complete. |
| `phase2.sh` | Executor wrapper: finds next step, runs Aider under a 15-minute timeout, commits on success. |
| `CompletedSteps.md` | Step completion log written and committed by `phase2.sh`. Tracks which steps are DONE. Committed (not gitignored) so branch state is self-describing. |
| `logs/ai-routing.csv` | Per-step routing log appended by `phase2.sh`: date, step, tier, outcome, approximate diff line count. |
| `docs/architecture.md` | Full architecture reference. |
| `docs/tabbyapi-nimbus-example.yml` | Reference TabbyAPI server settings (model, `max_seq_len`, KV cache mode) for the local executor. |
| `PHASE1_VERIFY_HELPER.md` | Stack-specific `verify.sh` quiet-log snippet (selected at scaffold time). Referenced by `PHASE1_SPEC.md` §4. |
| `.aider.conf.yml` | Aider config (Path C defaults: local TabbyAPI, `map-tokens: 0`, `edit-format: diff`). `phase2.sh` overrides to `--edit-format whole` when every target is whole-safe (new, or an existing file ≤ ~120 lines / `PHASE2_WHOLE_FILE_MAX_LINES`); a single oversized existing target keeps the step on `diff`. |
| `.aiderignore` | Files Aider must not read (secrets, env, credentials). |

## Quota budget (rough estimates)

- Plan: ~50K Claude tokens per feature.
- Execute: 0 Claude tokens (all local).
- Review: ~30K Claude tokens.
- Optional fix loop: ~30K.

These figures are unmeasured guesses — once you have a few features through the loop, replace them with the actual numbers from `logs/ai-routing.csv`.
