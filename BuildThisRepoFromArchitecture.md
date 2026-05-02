# BuildThisRepoFromArchitecture.md — nimbus-tiers Template Repo

**Date:** 2026-04-28
**Branch:** `claude/create-architecture-plan-SFwBL`
**Planner:** Claude (Opus 4.7)
**Estimated steps:** 13
**Source architecture:** [`hybrid-ai-coding-architecture-v2_1.md`](./hybrid-ai-coding-architecture-v2_1.md)

---

## Objective

Turn this repo (`nimbus-tiers`) into a reusable **template repository** that scaffolds new projects pre-wired for the Hybrid AI Coding Architecture (Plan → Execute → Review). The repo ships two Python CLIs:

1. **`generateNewProject.py`** — creates a new project folder one directory above this repo, copies template files (CONTEXT.md, VERIFY.md, CLAUDE.md, `.aider.conf.yml`, `.aiderignore`, `.gitignore`, `plans/`, `logs/`, `docs/architecture.md`, README.md) into it, and runs `git init` + an initial commit. Idempotent (skip-existing by default; `--force` and `--diff` flags available).
2. **`setupEnvironment.py`** — checks the host machine for the Path C runtime stack (NVIDIA driver, Ollama, TabbyAPI/ExLlamaV3, Aider, Claude Code, env vars) and offers to install/configure each missing piece. Idempotent — never overrides anything already present without explicit user confirmation.

Path C (Full Hybrid: Ollama + TabbyAPI/ExLlamaV3) is the only fully-implemented setup path. Paths A (Cloud-Only) and B (Light Local) are scaffolded as stub classes so they can be filled in later without re-architecting.

## Out of Scope

- Implementing Path A (Cloud-Only) or Path B (Light Local) — stubs only, raising `NotImplementedError`.
- Auto-installing NVIDIA drivers / CUDA / Visual Studio Build Tools — `setupEnvironment.py` only **checks** for these and tells the user what to install, since they need elevated permissions and reboot.
- Pulling actual model weights — the script can offer to run `ollama pull qwen2.5-coder:14b`, but won't download tens of GB without explicit user OK.
- Building a UI. Both scripts are CLI-only.
- Generating per-feature `PLAN.md` and `TESTS.md` — those are produced by Claude Code in Phase 1 inside the *new* project, not the template.

---

## Target Repo Layout (when this plan is complete)

```
nimbus-tiers/
├── hybrid-ai-coding-architecture-v2_1.md   (already exists)
├── BuildThisRepoFromArchitecture.md         (this file)
├── ProgressBuildingRepo.md                  (resume tracker)
├── README.md                                (template-repo usage instructions)
├── .gitignore
├── pyproject.toml                           (stdlib-only; metadata + entry points)
├── generateNewProject.py                    (thin CLI shim → src.nimbus_tiers.generator)
├── setupEnvironment.py                      (thin CLI shim → src.nimbus_tiers.environment)
├── src/
│   └── nimbus_tiers/
│       ├── __init__.py
│       ├── generator/
│       │   ├── __init__.py
│       │   ├── file_writer.py            (FileWriter: skip/force/diff modes)
│       │   ├── setup_path.py             (SetupPath ABC)
│       │   ├── full_hybrid_path.py       (FullHybridPath — only concrete impl)
│       │   ├── cloud_only_path.py        (CloudOnlyPath — stub)
│       │   ├── light_local_path.py       (LightLocalPath — stub)
│       │   ├── project_generator.py      (ProjectGenerator orchestrator)
│       │   └── git_initializer.py        (GitInitializer: init + initial commit)
│       └── environment/
│           ├── __init__.py
│           ├── setup_step.py             (SetupStep ABC: check() + install())
│           ├── environment_setup.py      (EnvironmentSetup orchestrator)
│           └── steps/
│               ├── __init__.py
│               ├── nvidia_driver_step.py
│               ├── python_step.py
│               ├── ollama_step.py
│               ├── tabbyapi_step.py
│               ├── aider_step.py
│               ├── claude_code_step.py
│               └── env_var_step.py
├── templates/                              (raw files copied verbatim into new projects)
│   ├── CONTEXT.md
│   ├── VERIFY.md
│   ├── CLAUDE.md
│   ├── README.md
│   ├── .aider.conf.yml
│   ├── .aiderignore
│   ├── .gitignore
│   ├── plans/README.md
│   ├── logs/ai-routing.csv
│   └── docs/architecture.md             (copy of hybrid-ai-coding-architecture-v2_1.md)
└── tests/
    ├── __init__.py
    ├── test_file_writer.py
    ├── test_full_hybrid_path.py
    ├── test_project_generator.py
    └── test_environment_steps.py
```

---

## Steps

### Step 1: Create top-level repo metadata
**File(s):** `README.md`, `.gitignore`, `pyproject.toml`
**Change:** Write a short `README.md` describing the template repo's purpose and the two CLIs. Write a `.gitignore` covering Python artifacts (`__pycache__/`, `*.pyc`, `.pytest_cache/`, `.venv/`, `dist/`, `build/`, `*.egg-info/`) plus `PLAN.md`/`TESTS.md` per the architecture doc. Write a minimal `pyproject.toml` declaring package metadata, Python `>=3.11`, no third-party deps, and console script entry points for `nimbus-generate` and `nimbus-setup`.
**Purpose:** Make the repo a valid Python package with discoverable entry points and developer onboarding docs.
**Edge cases:** Don't commit a `setup.py` — `pyproject.toml` only. Keep `pyproject.toml` build-system as `setuptools` (stdlib-friendly). No Poetry/Hatch/UV requirement.
**Tests:** `python -m build` succeeds (manual check); `pip install -e .` from the repo root creates the entry points.

### Step 2: Build `templates/` directory
**File(s):** `templates/CONTEXT.md`, `templates/VERIFY.md`, `templates/CLAUDE.md`, `templates/README.md`, `templates/.aider.conf.yml`, `templates/.aiderignore`, `templates/.gitignore`, `templates/plans/README.md`, `templates/logs/ai-routing.csv`, `templates/docs/architecture.md`
**Change:** Populate each template with the content prescribed by the architecture doc:
  - `CONTEXT.md` / `VERIFY.md` — Appendix E templates with `{{PROJECT_NAME}}` placeholder for repo name.
  - `CLAUDE.md` — project memory file telling Claude Code to read PLAN.md, TESTS.md, CONTEXT.md, VERIFY.md and follow the routing rules from `docs/architecture.md`.
  - `.aider.conf.yml` — Path C config (TabbyAPI at `http://localhost:5000/v1`, `model: openai/Qwen3-32B-exl3`, `auto-commits: true`, `auto-test: true`, `test-cmd: pytest -x --no-header`).
  - `.aiderignore` — `.env`, `.env.*`, `secrets/`, `**/credentials.*`, `**/api_keys.*`.
  - `.gitignore` — Python artifacts + `PLAN.md`, `TESTS.md`, `.aider.tags.cache.v3/`.
  - `plans/README.md` — short description: this directory archives completed PLAN.md files, named like `YYYY-MM-feature-name.md`.
  - `logs/ai-routing.csv` — header row only: `date,repo,task_type,tier_used,model,escalated_from,tests_passed,diff_lines_approx,human_rework_minutes,outcome`.
  - `docs/architecture.md` — verbatim copy of `hybrid-ai-coding-architecture-v2_1.md`.
  - `README.md` — short Plan→Execute→Review explainer with links into `docs/architecture.md`.
**Purpose:** All scaffolded artifacts live as plain files on disk; the generator just copies them. No template engine needed beyond simple string replacement of `{{PROJECT_NAME}}`.
**Edge cases:** Keep `{{PROJECT_NAME}}` the only placeholder so the substitution logic stays trivial. Hidden dotfiles (`.aider.conf.yml`, `.aiderignore`, `.gitignore`) need to be copied to corresponding hidden destinations — verify the copy code preserves the leading dot.
**Tests:** Each template file exists, is non-empty, and `grep -l '{{PROJECT_NAME}}'` shows substitution markers only where expected.

### Step 3: Implement `FileWriter` with idempotency policy
**File(s):** `src/nimbus_tiers/generator/file_writer.py`, `tests/test_file_writer.py`
**Change:** Create a `FileWriter` class with three modes — `SKIP` (default; warn + skip if dest exists), `FORCE` (overwrite), `DIFF` (print unified diff vs. existing dest, write nothing). Single public method `write(src_path: Path, dest_path: Path, substitutions: dict[str, str] | None = None) -> WriteResult`. `WriteResult` is a dataclass with `action: Literal["written", "skipped", "diffed"]` and `dest: Path`.
**Purpose:** Centralize the "check before override" requirement so every file copy is consistent and testable.
**Edge cases:** Create parent directories as needed. If `dest_path` exists and is a directory but `src_path` is a file (or vice versa), raise `IsADirectoryError`/`NotADirectoryError`. Substitution must apply to text files only — detect binary by attempting UTF-8 decode and falling back to raw bytes copy if it fails.
**Tests:** Unit tests covering each of the three modes for: new file, existing identical file, existing different file, file with `{{PROJECT_NAME}}` placeholder, binary file (use a small PNG or arbitrary `bytes`), nested destination requiring `mkdir -p`.

### Step 4: Implement `SetupPath` ABC and `FullHybridPath`
**File(s):** `src/nimbus_tiers/generator/setup_path.py`, `src/nimbus_tiers/generator/full_hybrid_path.py`, `tests/test_full_hybrid_path.py`
**Change:**
  - `SetupPath` (ABC): defines `name: str` (class attr), `template_files() -> list[TemplateSpec]` (abstract), `post_copy_hooks(project_root: Path) -> None` (default no-op). `TemplateSpec` is a dataclass with `src_relative: Path`, `dest_relative: Path`.
  - `FullHybridPath` (concrete): `name = "full-hybrid"`. `template_files()` returns the full list of files from Step 2 mapped to their destinations in the new project. `post_copy_hooks` is no-op for now (git init is handled by `ProjectGenerator`, not the path).
**Purpose:** OOP boundary that lets future paths (`CloudOnlyPath`, `LightLocalPath`) plug in by subclassing `SetupPath` and returning a different file list. The orchestrator is path-agnostic.
**Edge cases:** `template_files()` must return paths *relative to the templates root* and *relative to the project root*. Absolute paths are forbidden — enforce with an assertion.
**Tests:** `FullHybridPath().template_files()` returns the expected list; every `src_relative` exists under `templates/`; no duplicate destinations.

### Step 5: Implement `ProjectGenerator` orchestrator
**File(s):** `src/nimbus_tiers/generator/project_generator.py`, `tests/test_project_generator.py`
**Change:** `ProjectGenerator` takes a `SetupPath` instance, a `FileWriter`, and a `GitInitializer` (Step 7) via constructor injection. Public method `generate(project_name: str, project_path: Path) -> GenerationReport` which: (1) creates `project_path` if missing, (2) iterates the path's `template_files()` and calls `FileWriter.write(...)` for each with `{"PROJECT_NAME": project_name}` substitution, (3) calls `path.post_copy_hooks(project_path)`, (4) calls `GitInitializer.initialize(project_path)`, (5) returns a `GenerationReport` (counts of written/skipped/diffed files plus git init result).
**Purpose:** Dependency-injected orchestrator keeps the generator testable (mock `FileWriter` + `GitInitializer` in tests) and lets us swap setup paths via constructor.
**Edge cases:** If `project_path` exists and is non-empty, generation must still proceed (idempotency — user might be re-running to add a missing file). If `project_path` is a file, fail loudly.
**Tests:** Generator with a mock `SetupPath` returning two `TemplateSpec`s, a mock `FileWriter`, and a mock `GitInitializer` produces a correct `GenerationReport`. Substitution dict is passed through. Re-running over an existing populated dir reports all-skipped.

### Step 6: Implement `generateNewProject.py` CLI
**File(s):** `generateNewProject.py`, `src/nimbus_tiers/generator/__init__.py`
**Change:** Top-level `generateNewProject.py` is a thin shim that imports and calls `nimbus_tiers.generator.cli:main`. The CLI:
  - Positional arg `project_name` (optional; if missing, interactive prompt).
  - `--path PATH` — override default destination (default: `<this-repo-parent>/<project_name>`).
  - `--force` — overwrite existing files.
  - `--diff` — preview without writing.
  - `--path-type {full-hybrid}` — currently only `full-hybrid`; `cloud-only` and `light-local` are accepted by argparse but raise `NotImplementedError` with a friendly message.
  - On completion, prints the `GenerationReport` summary plus next-step instructions (cd into the new dir, open Claude Code, write a PLAN.md).
**Purpose:** User-facing entry point, satisfies the "one directory above the checked out repo" UX from the requirements.
**Edge cases:** Project name validation — must match `^[a-zA-Z0-9_-]+$`. If `--path` is relative, resolve against CWD, not the repo root. Refuse to generate into the template repo itself.
**Tests:** Smoke test in Step 12.

### Step 7: Implement `GitInitializer`
**File(s):** `src/nimbus_tiers/generator/git_initializer.py`
**Change:** `GitInitializer` class with method `initialize(project_path: Path) -> GitInitResult`. Behavior: if `.git/` already exists, skip with a warning. Otherwise run `git init`, `git add .`, `git commit -m "Initial scaffold from nimbus-tiers architecture template"`. Never sets a remote, never pushes. Uses `subprocess.run(check=True, capture_output=True)`.
**Purpose:** Self-contained git bootstrap so the new project is on a clean trunk from step zero.
**Edge cases:** If `git` is not on PATH, fail with a clear error message (don't crash the whole generation — return a `GitInitResult.skipped` with reason). If `git config user.email` is unset, the commit will fail — surface that error verbatim and tell the user to set their git identity.
**Tests:** Run against a tempdir; verify `.git/` is created and `git log` shows the expected commit. Re-run; verify it skips.

### Step 8: Implement `SetupStep` ABC + concrete check/install steps for Path C
**File(s):** `src/nimbus_tiers/environment/setup_step.py`, `src/nimbus_tiers/environment/steps/*.py`, `tests/test_environment_steps.py`
**Change:**
  - `SetupStep` (ABC): `name: str`, `check() -> CheckResult` (abstract; returns `present`/`missing`/`partial` + detail string), `install(interactive: bool) -> InstallResult` (abstract; performs install, returns `installed`/`skipped`/`failed`). Default `install` raises `NotImplementedError` with a "manual step required" message — useful for steps like NVIDIA driver where we can only check.
  - Concrete steps:
    - `NvidiaDriverStep` — runs `nvidia-smi`, parses driver version, requires `>= 572.16`. Install is manual (prints instructions).
    - `PythonStep` — checks `sys.version_info >= (3, 11)`. Install manual.
    - `OllamaStep` — checks `ollama --version`; install via `curl -fsSL https://ollama.com/install.sh | sh` (Linux/WSL only) — asks before running. Also checks `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` and offers to add them to `~/.bashrc`.
    - `TabbyApiStep` — checks for a `tabbyapi/` checkout in a configured location (default `~/tabbyapi`); offers to clone + run `start.py` non-interactively.
    - `AiderStep` — checks `aider --version`; install via `pip install aider-install && aider-install`.
    - `ClaudeCodeStep` — checks `claude --version`; if missing, prints install instructions (npm-based; we don't auto-install).
    - `EnvVarStep` — generic, takes `(name, expected_value, shell_rc_path)` constructor args; checks current env, offers to append `export NAME=VALUE` to the rc file.
**Purpose:** One class per dependency keeps the environment setup readable and lets us add Path A/B steps later by composing different lists.
**Edge cases:** All `install()` calls must prompt before doing anything, regardless of `interactive=True`. Honor a top-level `--yes` flag passed down from `setupEnvironment.py` to skip prompts in CI. Never write to system files (`/etc/...`); only user-scope files (`~/.bashrc`, `~/.profile`).
**Tests:** Each step's `check()` is unit-tested with a mocked `subprocess.run` returning known stdout/stderr/returncode. `install()` paths use a mock prompt function and verify the right commands would be run (without actually running them).

### Step 9: Implement `EnvironmentSetup` orchestrator + `setupEnvironment.py` CLI
**File(s):** `src/nimbus_tiers/environment/environment_setup.py`, `setupEnvironment.py`
**Change:** `EnvironmentSetup` takes a list of `SetupStep`s and runs them in order. For each step: call `check()`, print status, and if missing/partial, prompt for install (unless `--yes`). Return a final report.

`setupEnvironment.py` shim:
  - `--yes` — non-interactive, accept all installs (use with caution).
  - `--check-only` — just run `check()` for every step, print the report, exit 0 if all present, 1 otherwise.
  - `--path-type {full-hybrid}` — selects which step list to use. Other path types raise `NotImplementedError`.
**Purpose:** Single-command host-machine readiness check.
**Edge cases:** Order matters — Python before pip-installed tools; NVIDIA driver before Ollama/TabbyAPI. Document the order in a docstring.
**Tests:** `EnvironmentSetup` orchestrator unit-tested with a list of fake `SetupStep`s.

### Step 10: Add stub `CloudOnlyPath` and `LightLocalPath`
**File(s):** `src/nimbus_tiers/generator/cloud_only_path.py`, `src/nimbus_tiers/generator/light_local_path.py`
**Change:** Both classes inherit `SetupPath`, set `name`, and override `template_files()` to raise `NotImplementedError("CloudOnlyPath is planned but not yet implemented. Track in BuildThisRepoFromArchitecture.md follow-ups.")`.
**Purpose:** Make the OOP extension point visible. Users who try `--path-type cloud-only` get a clear "not yet" error, not a `KeyError`.
**Edge cases:** Don't accidentally register them in the CLI argparse choices in a way that hides the not-implemented error — they should be argparse-accepted so the user gets the descriptive `NotImplementedError`.
**Tests:** Instantiating either class is fine; calling `template_files()` raises `NotImplementedError`.

### Step 11: Add unit tests for core components
**File(s):** `tests/test_file_writer.py`, `tests/test_full_hybrid_path.py`, `tests/test_project_generator.py`, `tests/test_environment_steps.py`
**Change:** Already specified inline in earlier steps. Pull together with `pytest` discovery (`conftest.py` if needed). Use only `pytest` and stdlib `unittest.mock` — no other test deps.
**Purpose:** Confidence the OOP seams hold up when Paths A/B are added.
**Edge cases:** Tests must not require Ollama, TabbyAPI, or `git` to be installed — mock all subprocess calls.
**Tests:** `pytest -x --no-header` passes.

### Step 12: End-to-end smoke test of `generateNewProject.py`
**File(s):** N/A (manual run)
**Change:** Run `python generateNewProject.py smoke-test --path /tmp/smoke-test` and verify: directory exists, every expected file is present and non-empty, `{{PROJECT_NAME}}` has been substituted to `smoke-test`, `.git/` exists, initial commit message matches. Re-run with no flags — verify everything reports "skipped". Re-run with `--diff` — verify a unified diff prints when a template file is intentionally modified in `/tmp/smoke-test`. Re-run with `--force` — verify the modification is overwritten.
**Purpose:** Real-world validation that the OOP layers, file writer, and git initializer compose correctly.
**Edge cases:** Clean up `/tmp/smoke-test` between scenarios.
**Tests:** All four runs behave as expected.

### Step 13: Final README polish, commit, and push
**File(s):** `README.md`, `ProgressBuildingRepo.md`
**Change:** Update `README.md` with verified usage examples from Step 12. Mark all steps complete in `ProgressBuildingRepo.md`. Commit with message `"Build nimbus-tiers template repo: generator + environment CLIs (Path C)"` and push to `claude/create-architecture-plan-SFwBL`.
**Purpose:** Ship a working state.
**Edge cases:** Don't push if any test fails. Don't commit smoke-test artifacts (`/tmp/smoke-test` is outside the repo, but double-check `git status`).
**Tests:** `git status` clean after commit; remote branch updated.

---

## Edge Cases & Risks

- **Hidden dotfiles in `templates/`** — git won't track an empty directory, and some tooling (including some shells' tab completion) hides files starting with `.`. Verify the templates are actually committed by checking `git ls-files templates/`.
- **`{{PROJECT_NAME}}` collision with legitimate content** — unlikely in markdown templates, but document the placeholder in `templates/README.md` so future maintainers don't accidentally write literal `{{PROJECT_NAME}}` text they want preserved.
- **WSL2 path translation** — if a Windows user runs `generateNewProject.py` from PowerShell against a WSL python, paths can get weird. Document in README that the script expects to run inside WSL2 (or native Linux/Mac).
- **`pip install -e .` adds package metadata** — make sure `.gitignore` excludes `*.egg-info/` so we don't accidentally commit it.
- **Paths A/B stub explosion** — when those paths are implemented later, they may want to share template files with Path C. Keep the templates/ directory flat and let `SetupPath` subclasses pick which subset to copy. Don't pre-create `templates/full-hybrid/` etc.
- **Git identity unset** — `GitInitializer` will fail at the commit step. Surface the underlying git error message verbatim and don't pretend it succeeded.
- **Architecture doc updates** — `templates/docs/architecture.md` is a copy. If the source `hybrid-ai-coding-architecture-v2_1.md` updates, the template copy goes stale. Add a CI check (or a `make sync-architecture` target) later. Out of scope for this plan.
