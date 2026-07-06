# nimbus-tiers — Repository Review & Feature Ratings

*Review date: 2026-07-06. Scope: full repo at `main` (commit `1373e34`).*

> **Addendum (2026-07-06, later the same day):** the two features rated under
> 3 stars have since been fixed — see the [addendum](#addendum-2026-07-06--sub-3-star-features-fixed)
> at the end of this document for the updated ratings. The ratings in the body
> below are kept as written, as a record of the state they reviewed.

## Overview

nimbus-tiers is a template repository for a three-phase "Hybrid AI Coding Architecture": plan with a frontier model (Claude Code), execute one small step at a time with a local model (Aider + Qwen2.5-Coder-14B via TabbyAPI), then review with the frontier model again. The repo ships two stdlib-only Python CLIs (`generateNewProject.py`, `setupEnvironment.py`), a template suite copied into new projects, and a heavily hardened `phase2.sh` executor script.

**Overall assessment: ★★★★ (4/5).** The engineering quality is well above what template repos usually get: dependency-injected, unit-tested Python; an executor script that encodes a genuinely impressive catalog of observed local-model failure modes; and documentation that explains *why* at every turn. The main weaknesses are distribution (the pip-installable packaging is effectively broken), the two unimplemented setup paths, the absence of CI, and the concentration of the most critical logic in a 1,424-line bash monolith.

---

## Feature ratings

### 1. Project scaffolder (`generateNewProject.py`, `nimbus-generate`) — ★★★★

`src/nimbus_tiers/generator/` is cleanly designed: a `SetupPath` ABC declares which template files a path copies (`setup_path.py`), `ProjectGenerator` orchestrates path + writer + git via constructor injection (`project_generator.py`), and the CLI layers name validation, package/class-name derivation, and stack selection on top (`cli.py`).

**Strengths:** four stacks (java-maven, java-gradle, python, node) with correct per-stack layout including Java package-directory mapping and `mvnw`/`gradlew` chmod hooks (`full_hybrid_path.py:132-136`); refuses to generate into the template repo itself (`cli.py:156-159`); duplicate-destination validation (`setup_path.py:61-70`); honest docstrings about edge cases (e.g. `derive_class_name` documenting the `weatherAPI` → `Weatherapi` quirk).

**Why not 5:** two of the three advertised setup paths are `NotImplementedError` stubs; the default destination ("one directory above this repo") is convention-heavy and surprises users who expect scaffolding into the CWD; class/package derivation is Java-centric but silently computed for all stacks.

### 2. Idempotent `FileWriter` (skip / force / diff modes) — ★★★★★

`file_writer.py` is the best small component in the repo. Three modes with an explicit `UNCHANGED` state for byte-identical files, `{{KEY}}` substitution applied only to UTF-8-decodable files with byte-for-byte binary passthrough, unified-diff preview mode, injectable logger, and directory/file mismatch errors. It does exactly one job, does it defensively, and has 12 dedicated tests. No meaningful criticism at this scale.

### 3. `GitInitializer` — ★★★★

`git_initializer.py` is small and correct: skips when `.git` exists, degrades gracefully when git is absent from PATH, reports failures with captured stderr instead of raising, and takes an injectable runner for tests. **Why not 5:** it doesn't handle hosts without `user.name`/`user.email` configured (the commit fails — accurately reported, per `ProgressBuildingRepo.md`, but a `-c user.name=...` fallback or a clearer hint would improve first-run experience), and there's no option for the initial branch name (`git init -b main`).

### 4. Environment setup (`setupEnvironment.py`, `nimbus-setup`) — ★★★★

The `SetupStep` check/install lifecycle (`setup_step.py`) is a solid pattern: `check()` is always safe, `install()` requires consent, non-installable steps return `MANUAL` with instructions, and everything (runner, confirm, logger, prompter) is injectable — which is why `test_environment_steps.py` can cover 68 cases without touching the host. The Ollama step's remote-endpoint option and rc-file persistence show real WSL-user empathy.

**Why not 5:** Linux/WSL-centric (procfs, apt/systemd assumptions, bash/zsh rc files only); `EnvVarStep.install` appends to the rc file unconditionally, so repeated runs can accumulate duplicate `export` lines; only the full-hybrid step list exists; and `--yes` piping `curl | sh` installers (`ollama_step.py:21`) deserves a louder warning.

### 5. Phase 2 executor (`templates/phase2.sh`) — ★★★★

This is the repo's crown jewel *and* its biggest liability. In 1,424 lines it implements: a lock with PID+starttime stale-lock recovery; branch guards (no master/detached HEAD); a WIP sentinel in `.git/` for interrupted-run recovery; dirty-tree guards with careful pathspec excludes; a live watchdog that kills degenerate repetition loops mid-generation; input-overflow vs. output-truncation failure classification with cause-matched guidance; preflight endpoint reachability, served-model reconciliation, and context-length floor checks; a build-file coordinate-corruption guard; a JVM dotted-directory path guard; `.gitignore` self-repair; markdown-fence scrubbing; per-step routing CSV; and opt-in automatic fallback-model escalation. Every guard's comment cites the concrete observed failure it prevents. As institutional knowledge about running sub-frontier local models, it is genuinely exceptional.

**Why not 5:** it is a monolith at the very edge of what bash should carry. The logic is only testable end-to-end (`test_phase2_guards.py` does this via subprocess, commendably), every new guard raises the cost of the next one, and a template file this large is copied verbatim into every generated project with no upgrade path (see improvement #5). The complexity is *earned*, but its current packaging is fragile.

### 6. Documentation & template suite — ★★★★½

`PHASE1_SPEC.md` (633 lines) as a single canonical spec referenced by both `CLAUDE.md` and `NIMBUS_GUIDE.md` — with an explicit note to keep the two prompt shells thin so policy can't diverge — is unusually disciplined. The architecture doc, README with PEP 668 guidance, per-stack `PHASE1_VERIFY.md` helpers, and the annotated `.aider.conf.yml` (which explains VRAM/quantization/KV-cache tradeoffs) are all high quality. The half-star deduction: total documentation volume (~5,000+ lines) is intimidating for onboarding, and some guidance lives in comments inside `phase2.sh` where users won't find it.

### 7. Test suite — ★★★★

155 tests across ~2,400 lines, enabled by consistent dependency injection. Coverage is broad: writer modes, path specs, generator orchestration, CLI arg handling, all eight environment steps, and — most valuably — subprocess-level tests of `phase2.sh`'s guards (`test_phase2_guards.py`, 562 lines) and spec-conformance tests for `PHASE1_SPEC.md`. **Why not 5:** no CI runs them (see below), so nothing enforces they pass on a contribution; and the bash guards are tested at the black-box level only, so a regression inside an untested guard branch can slip through.

### 8. Packaging & distribution — ★★

The stdlib-only, zero-dependency choice is right for a bootstrap tool. But the pip-install story advertised in the README is effectively broken: `[tool.setuptools.package-data]` points at `"../../templates/**/*"` (`pyproject.toml:44-45`), which does not package files living outside `src/` into a wheel, and `generator/cli.py:40` locates templates via `Path(__file__).resolve().parents[3]` — correct in a repo clone, wrong under `site-packages`. So `pipx install .` yields a `nimbus-generate` that can't find its templates. Works fine as a cloned repo (the primary documented flow), hence 2 stars rather than 1. Also: `pyproject.toml` declares MIT but **no LICENSE file exists in the repo**.

### 9. Setup-path extensibility (Paths A & B stubs) — ★★

`cloud_only_path.py` and `light_local_path.py` are honest 19-line stubs that raise `NotImplementedError` with a helpful message, and the ABC means implementing them requires no orchestrator changes. But as shipped features they deliver nothing yet, and the CLI advertising them in `--path-type` choices makes the gap more visible.

---

## Improvements & new features (rated by value)

### 1. Add CI (GitHub Actions: pytest + shellcheck) — ★★★★★

There is no `.github/` directory. A repo whose core value is *automated verification discipline* has no automated verification of itself — the 155-test suite only runs when someone remembers to. A single workflow running `pytest` on 3.11–3.13 plus `shellcheck templates/phase2.sh` would catch regressions in the guards that the whole architecture depends on. Highest value-to-effort ratio available.

### 2. Fix packaging or retract the pip-install claim — ★★★★

Either move `templates/` under `src/nimbus_tiers/templates/` (packaged via `package-data`, located via `importlib.resources`) or remove the console-script/pipx section from the README. Right now the README actively recommends `pipx install .` (Option B) which produces a broken binary. Silent breakage of a documented flow justifies 4 stars despite the flow being secondary.

### 3. Add the LICENSE file — ★★★★

`pyproject.toml` declares MIT; no `LICENSE` file exists. Without it the code is legally all-rights-reserved by default and the metadata is misleading. Five-minute fix, real consequence for anyone reusing the template — only not 5 stars because it affects legal hygiene, not functionality.

### 4. Implement Path B (Light Local) — ★★★★

The architecture's most accessible tier — Ollama only, no TabbyAPI/ExLlamaV3, no 16GB-GPU requirement — is the one most prospective users can actually run, and it's a stub. The `SetupPath`/`SetupStep` abstractions were built precisely so this could be added without restructuring; most template files are shared. Path A (Cloud-Only) is worth doing after (★★★) since cloud users have less need of the scaffolding's local-model guardrails.

### 5. A template upgrade path for generated projects (`nimbus-update`) — ★★★★

`phase2.sh` is copied into every generated project and then never sees fixes again — yet the git log shows it receiving critical guard fixes continuously (5 of the last 8 PRs). A command that re-diffs a generated project's scaffold files against the current templates (the `FileWriter` DIFF mode already does 80% of this) and selectively updates them would let existing projects inherit fixes. Without it, every improvement to phase2.sh strands all previously generated projects.

### 6. Make phase2.sh's guards independently testable — ★★★★

Extract the pure-logic guards (path parsing/`_strip_md_path`, JVM path regex, no-change detection, token-limit classification) into a sourceable `phase2-lib.sh` with bats tests, or port the driver to Python (the repo already ships Python; the script already shells out to `python3` for step counting at line 157). Keeps the hard-won behavior, cuts the regression risk that grows with every added guard. Rated below CI only because the subprocess tests partially cover this today.

### 7. `phase2.sh --status` / `--dry-run` — ★★★

Today the only way to see pipeline state (next step, WIP sentinel present, fail marker armed, dirty tree, lock held) is to read `.git/` internals or start a run. A read-only status mode would make the recovery machinery legible to users instead of just to the script — important because the script's failure messages already ask users to reason about sentinels.

### 8. Routing-log analyzer (`nimbus-stats`) — ★★★

`logs/ai-routing.csv` is written on every step (tier, model, escalation, outcome, diff size) but nothing reads it, and the `human_rework_minutes` column is never populated. A small stdlib CLI summarizing escalation rate, failure rate by step type, and local-vs-fallback share would close the feedback loop the architecture doc promises ("route by data, not vibes"). 3 stars: valuable, but only after enough runs accumulate data.

### 9. Duplicate-append guard in `EnvVarStep` / rc-file writes — ★★★

`EnvVarStep.install` and `append_rc_export` (`setup_step.py:70-74, 213-233`) append unconditionally; re-running setup after declining a shell restart stacks duplicate `export` lines in `.bashrc`. The fix is small (read-check via the existing `read_bashrc_value` before appending). Low effort, removes the one place the setup tool violates its own idempotency promise.

### 10. More stacks: Go and Rust — ★★★

`STACK_TEST_COMMANDS` + a `templates/stacks/<name>/` directory is all a new stack needs, and Go/Rust single-binary projects suit small local-model steps well (fast builds, strict compilers = strong verify.sh gates). 3 stars: pure breadth, no architectural risk, but doesn't fix any current weakness.

### 11. Windows/macOS support for `setupEnvironment.py` — ★★

The checks assume Linux/WSL (procfs in phase2.sh's lock recovery, `nvidia-smi`, bash/zsh rc files, GNU timeout probing). Native macOS (Apple Silicon + Ollama) is a plausible audience; native Windows less so given the WSL framing. Real effort, moderate audience — worth doing only after Paths A/B exist.

### 12. Interactive wizard mode for `nimbus-generate` — ★★

A guided prompt flow (choose path → stack → name, with explanations) would help first-time users, but the current one-command CLI with good `--help` text already serves the target audience (developers comfortable with terminals). Nice-to-have polish, lowest priority here.

---

## Summary

| # | Feature | Rating |
|---|---------|--------|
| 1 | Project scaffolder | ★★★★ |
| 2 | FileWriter (skip/force/diff) | ★★★★★ |
| 3 | GitInitializer | ★★★★ |
| 4 | Environment setup CLI | ★★★★ |
| 5 | phase2.sh executor | ★★★★ |
| 6 | Docs & template suite | ★★★★½ |
| 7 | Test suite | ★★★★ |
| 8 | Packaging & distribution | ★★ |
| 9 | Setup-path stubs (A/B) | ★★ |

| # | Improvement | Value |
|---|-------------|-------|
| 1 | CI: pytest + shellcheck workflow | ★★★★★ |
| 2 | Fix wheel packaging or retract pipx claim | ★★★★ |
| 3 | Add LICENSE file (MIT declared, absent) | ★★★★ |
| 4 | Implement Path B (Light Local) | ★★★★ |
| 5 | `nimbus-update` template-drift upgrader | ★★★★ |
| 6 | Testable phase2.sh guard library | ★★★★ |
| 7 | `phase2.sh --status` / `--dry-run` | ★★★ |
| 8 | Routing-log analyzer | ★★★ |
| 9 | Idempotent rc-file appends | ★★★ |
| 10 | Go/Rust stacks | ★★★ |
| 11 | macOS/Windows portability | ★★ |
| 12 | Generator wizard mode | ★★ |

---

## Addendum (2026-07-06) — sub-3-star features fixed

Both features rated under 3 stars were reworked in the two commits on
`claude/fix-sub-3-star-features` (`cb33ea3`, `1264ebc`), immediately after
this review. Updated ratings:

### 8. Packaging & distribution — ★★ → ★★★★

The templates tree now lives inside the package (`src/nimbus_tiers/templates/`)
and is resolved via `importlib.resources` (`nimbus_tiers/resources.py`), so
wheels ship all 38 template files — including the dotfiles, which required
explicit dot-prefixed package-data globs. `pipx install .` now produces a
working `nimbus-generate`: verified by installing the wheel into a clean venv
and scaffolding all three path types from an unrelated directory. The default
destination is unchanged from a source checkout (sibling of the repo) and
falls back to `<cwd>/<name>` when installed. The missing MIT `LICENSE` file
was added to match the pyproject metadata. **Why not 5:** no CI yet publishes
or re-verifies the wheel on each change (improvement #1 still open), and the
sdist/wheel build was only exercised locally.

### 9. Setup paths A & B — ★★ → ★★★★

`CloudOnlyPath` and `LightLocalPath` are no longer stubs. The shared scaffold
moved into a `StackScaffoldPath` base; each path contributes its own Aider
config under `templates/paths/<name>/`:

- **light-local** targets Ollama's OpenAI-compatible endpoint on
  `localhost:11434` with an Ollama-specific anti-looping serving checklist;
  `phase2.sh` needed no changes because its preflight already degrades
  gracefully on non-TabbyAPI servers.
- **cloud-only** targets `groq/llama-3.3-70b-versatile` via `GROQ_API_KEY`,
  which the existing phase2.sh preflight already enforces.

`nimbus-setup` gained matching per-path step lists (light-local drops
TabbyAPI; cloud-only checks only Python, Aider, Groq key, Claude Code), and
the stub tests were replaced with per-path file-list, config-content, and
step-list contracts (suite: 204 → 255 tests). **Why not 5:** neither path has
been exercised against a live Ollama or Groq endpoint end-to-end yet, and the
guide/architecture docs still narrate the Full Hybrid path as the primary
worked example (a note now points readers to their path's `.aider.conf.yml`).

With these fixes, improvements #2 (packaging), #3 (LICENSE), and #4
(Path B, plus Path A) from the backlog are done. The top remaining item is
unchanged: **#1, add CI** — nothing yet re-runs the 255 tests or rebuilds the
wheel on each change.
