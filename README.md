# nimbus-tiers

A template repository for the **Hybrid AI Coding Architecture** (Plan → Execute → Review). Clone this once, then run `generateNewProject.py` to scaffold a new project that's pre-wired for the routing flow described in [`hybrid-ai-coding-architecture-v2_1.md`](./hybrid-ai-coding-architecture-v2_1.md).

## What this repo gives you

Two stdlib-only Python CLIs:

- **`generateNewProject.py`** — creates a new project folder *one directory above this repo* (or under the current directory when running the installed `nimbus-generate`), copies template files (`CONTEXT.md`, `VERIFY.md`, `CLAUDE.md`, `.aider.conf.yml`, `.aiderignore`, `.gitignore`, `plans/`, `logs/`, `docs/architecture.md`, `NIMBUS_GUIDE.md`) into it, then runs `git init` + an initial commit. Idempotent: existing files are skipped by default.
- **`setupEnvironment.py`** — checks the host machine for the runtime stack required by Path C (Full Hybrid: NVIDIA driver, Ollama, TabbyAPI/ExLlamaV3, Aider, Claude Code, env vars). Prompts before installing or modifying anything.

## Step-by-step: from zero to first coding session

Follow these steps in order. No installation is required beyond Python 3.11+.

**Step 1 — Clone this repo**

```bash
git clone https://github.com/invaderfry/nimbus-tiers
cd nimbus-tiers
```

**Step 2 — (Optional but recommended) Check your environment**

This tells you whether the required tools (NVIDIA driver, Ollama, TabbyAPI, Aider, Claude Code) are already present. Nothing is installed — it only reports what's missing.

```bash
python3 setupEnvironment.py --check-only
```

If anything is missing, run the same command without `--check-only` and it will prompt you before installing each item:

```bash
python3 setupEnvironment.py
```

**Step 3 — Scaffold a new project**

This creates `../my-app` (one directory above this repo), copies all template files into it, and runs `git init` + an initial commit.

```bash
python3 generateNewProject.py my-app
```

Replace `my-app` with your actual project name (letters, numbers, dashes, underscores).

Use `--stack` to tell the generator which tech stack you're targeting. This sets the `test-cmd` in `.aider.conf.yml` so Aider runs the right test command automatically:

| `--stack` | Aider `test-cmd` |
|---|---|
| `java-maven` *(default)* | `./mvnw test` |
| `java-gradle` | `./gradlew test` |
| `node` | `npm test` |
| `python` | `pytest -x --no-header` |

```bash
# Java Spring Boot (Maven) — default, no flag needed
python3 generateNewProject.py my-app

# Java Spring Boot (Gradle)
python3 generateNewProject.py my-app --stack java-gradle

# Node.js
python3 generateNewProject.py my-app --stack node

# Python
python3 generateNewProject.py my-app --stack python
```

**Step 4 — cd into your new project**

```bash
cd ../my-app
```

**Step 5 — Phase 1: Plan (Claude Code)**

Open Claude Code and use it to write `PLAN.md`, `TESTS.md`, per-step files in `plans/`, and to refine the `CONTEXT.md` that was scaffolded for you.

```bash
claude
```

Use the Phase 1 starter prompt in `NIMBUS_GUIDE.md`. Claude will write `plans/step01.md`, `step02.md`, etc. — one file per step, sized to fit within the local model's 10K token context window.

**Step 6 — Phase 2: Execute (Aider)**

Run the executor wrapper. Re-run it until all steps show DONE:

```bash
./phase2.sh
```

Each run loads one step file, runs `./verify.sh`, commits on success, and stops. Token usage stays well within the local model's context window because only one step file is loaded at a time.

**Step 7 — Phase 3: Review (Claude Code)**

Return to Claude Code to review the diff Aider produced against the original plan.

```bash
claude
```

Ask Claude to compare the changes against `PLAN.md` and `TESTS.md` and identify anything missing or incorrect.

---

## `nimbus-generate` vs `python3 generateNewProject.py` — what's the difference?

They run **identical code**. `generateNewProject.py` is a thin shim that imports and calls the same internal function (`nimbus_tiers.generator.cli:main`) that the `nimbus-generate` console-script alias also calls. The difference is only in how you invoke them:

| | `python3 generateNewProject.py` | `nimbus-generate` |
|---|---|---|
| Install required? | No — works right after `git clone` | Yes — requires `pip install -e .` or `pipx install .` first |
| Must run from repo dir? | Yes | No — it's a global command, callable from anywhere |
| Arguments / flags | Identical | Identical |

**Use `python3 generateNewProject.py`** when you just cloned the repo and want to get started immediately.

**Use `nimbus-generate`** when you want a global command so you don't have to `cd` back into the nimbus-tiers repo each time you scaffold a new project. The same applies to `nimbus-setup` vs `python3 setupEnvironment.py`.

One behavioral difference: the **default destination** depends on how you run it. From a source checkout the new project is created *one directory above the repo* (as documented in the quick start). From an installed package (`pipx install .` — there is no repo to be a sibling of) it is created *under the current working directory*. Pass `--path` to choose explicitly in either mode. The templates ship inside the package (`nimbus_tiers/templates/`), so the installed commands work from anywhere.

---

## Quick start

The two top-level scripts (`generateNewProject.py`, `setupEnvironment.py`) are self-contained — they add `src/` to `sys.path` themselves, so **no install is required to use them**:

```bash
# 1. scaffold a new project (creates ../my-app and git-inits it)
# Default stack is java-maven; pass --stack python/java-gradle/node to override
python3 generateNewProject.py my-app

# 2. (optional) bring up the Path C runtime stack on this machine
python3 setupEnvironment.py --check-only

# 3. cd into the new project and start the Plan → Execute → Review flow
cd ../my-app
claude          # Phase 1: write PLAN.md, TESTS.md, plans/step01.md…, refine CONTEXT.md
./phase2.sh     # Phase 2: re-run until all steps DONE (one commit per step)
claude /review  # Phase 3
```

`phase2.sh --status` prints a read-only pipeline report (next step, lock/sentinel state, dirty tree, gate lint) and `phase2.sh --dry-run` exercises every pre-Aider check without invoking the model or touching the tree.

### Optional: install as a Python package

If you want global `nimbus-generate` / `nimbus-setup` / `nimbus-update` console-script aliases, install the package. **On modern Debian/Ubuntu/WSL (PEP 668)**, the system Python refuses `pip install` outside a venv — pick one of these:

```bash
# Option A — venv (recommended for development)
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"

# Option B — pipx (for global CLI access)
sudo apt install pipx
pipx install .

# Option C — only if you understand the risks (NOT recommended)
pip install -e . --break-system-packages
```

If you see `error: externally-managed-environment` from pip, that's PEP 668. Use a venv or pipx — don't use `--break-system-packages` on your system Python.

## Setup paths

The architecture defines three setup paths. All three are implemented; they share the same project skeleton (`phase2.sh`, `PHASE1_SPEC.md`, stack starters, …) and differ in the Aider executor config (`.aider.conf.yml`) that gets copied in, plus which tools `setupEnvironment.py` checks for. Select one with `--path-type` on either CLI (default: `full-hybrid`):

| Path | Description | Executor endpoint | Environment checks |
|---|---|---|---|
| A — Cloud-Only | Groq + Claude/ChatGPT subscriptions, no local models | Groq API (`GROQ_API_KEY`) | Python, Aider, Groq key, Claude Code |
| B — Light Local | Ollama only, no TabbyAPI | Ollama OpenAI-compatible API on `localhost:11434` | Python, NVIDIA driver, Ollama (+ server config), Aider, Groq key, Claude Code |
| C — Full Hybrid | Ollama + TabbyAPI/ExLlamaV3 + cloud subscriptions | TabbyAPI on `localhost:5000` | All of the above plus TabbyAPI |

```bash
# scaffold against Ollama instead of TabbyAPI
python3 generateNewProject.py my-app --path-type light-local --stack python
python3 setupEnvironment.py --path-type light-local

# no local models at all — execute steps on Groq
python3 generateNewProject.py my-app --path-type cloud-only --stack python
python3 setupEnvironment.py --path-type cloud-only
```

## Updating an existing project

`phase2.sh` and the other tool-owned scaffold files keep receiving fixes in this repo, but a generated project holds a frozen copy from generation day. `updateProject.py` / `nimbus-update` re-syncs the **managed** subset — `phase2.sh`, `phase2-lib.sh`, `PHASE1_SPEC.md`, `NIMBUS_GUIDE.md`, `PHASE1_VERIFY_HELPER.md`, `.aiderignore`, and the docs — without touching user-owned files (`CONTEXT.md`, `VERIFY.md`, `CLAUDE.md`, `.aider.conf.yml`, `.gitignore`, your source code):

```bash
cd ../my-app
python3 ../nimbus-tiers/updateProject.py             # preview (unified diff, writes nothing)
python3 ../nimbus-tiers/updateProject.py --apply     # overwrite managed files that changed
```

`--apply` refuses to run on a dirty git tree so the update always lands as a single reviewable commit. Which path/stack the project uses is read from the `.nimbus-tiers.json` manifest the generator writes; projects generated before the manifest existed pass `--path-type` and `--stack` explicitly. `--force-all` extends the update to user-owned files (destroys local edits — commit first).

## Idempotency

All three CLIs check before overwriting anything:

- `generateNewProject.py` — defaults to **skip + warn** for existing files. Use `--force` to overwrite, `--diff` to preview without writing.
- `setupEnvironment.py` — never writes to your machine without an interactive prompt. Use `--check-only` to see what's missing without prompting.
- `updateProject.py` — defaults to **diff preview**; `--apply` only overwrites managed files whose content actually differs.

## Development

```bash
# create and activate a venv (required on PEP 668 systems like Ubuntu 23.04+/WSL)
python3 -m venv .venv
source .venv/bin/activate

# install with test deps
pip install -e ".[test]"

# run the test suite
pytest -x --no-header
```

## Documentation

- [`hybrid-ai-coding-architecture-v2_1.md`](./hybrid-ai-coding-architecture-v2_1.md) — the architecture this repo scaffolds.
- [`BuildThisRepoFromArchitecture.md`](./BuildThisRepoFromArchitecture.md) — the implementation plan for the template repo itself.
- [`ProgressBuildingRepo.md`](./ProgressBuildingRepo.md) — execution status of that plan.
