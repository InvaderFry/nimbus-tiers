# nimbus-tiered

A template repository for the **Hybrid AI Coding Architecture** (Plan → Execute → Review). Clone this once, then run `generateNewProject.py` to scaffold a new project that's pre-wired for the routing flow described in [`hybrid-ai-coding-architecture-v2_1.md`](./hybrid-ai-coding-architecture-v2_1.md).

## What this repo gives you

Two stdlib-only Python CLIs:

- **`generateNewProject.py`** — creates a new project folder *one directory above this repo*, copies template files (`CONTEXT.md`, `VERIFY.md`, `CLAUDE.md`, `.aider.conf.yml`, `.aiderignore`, `.gitignore`, `plans/`, `logs/`, `docs/architecture.md`, `README.md`) into it, then runs `git init` + an initial commit. Idempotent: existing files are skipped by default.
- **`setupEnvironment.py`** — checks the host machine for the runtime stack required by Path C (Full Hybrid: NVIDIA driver, Ollama, TabbyAPI/ExLlamaV3, Aider, Claude Code, env vars). Prompts before installing or modifying anything.

## Quick start

```bash
# 1. (one time) install this template repo locally as a Python package
pip install -e .

# 2. scaffold a new project (creates ../my-app and git-inits it)
python generateNewProject.py my-app

# 3. (optional) bring up the Path C runtime stack on this machine
python setupEnvironment.py

# 4. cd into the new project and start the Plan → Execute → Review flow
cd ../my-app
claude          # Phase 1: write PLAN.md, TESTS.md, refine CONTEXT.md
aider --read PLAN.md --read TESTS.md --read CONTEXT.md   # Phase 2
claude /review  # Phase 3
```

## Setup paths

The architecture defines three setup paths. This repo currently implements **Path C (Full Hybrid)** end-to-end. Paths A and B are scaffolded as OOP extension points so they can be added later without restructuring:

| Path | Description | Status |
|---|---|---|
| A — Cloud-Only | Groq + Claude/ChatGPT subscriptions, no local models | Stub (raises `NotImplementedError`) |
| B — Light Local | Ollama only, no TabbyAPI | Stub (raises `NotImplementedError`) |
| C — Full Hybrid | Ollama + TabbyAPI/ExLlamaV3 + cloud subscriptions | **Implemented** |

## Idempotency

Both CLIs check before overwriting anything:

- `generateNewProject.py` — defaults to **skip + warn** for existing files. Use `--force` to overwrite, `--diff` to preview without writing.
- `setupEnvironment.py` — never writes to your machine without an interactive prompt. Use `--check-only` to see what's missing without prompting.

## Development

```bash
# install with test deps
pip install -e ".[test]"

# run the test suite
pytest -x --no-header
```

## Documentation

- [`hybrid-ai-coding-architecture-v2_1.md`](./hybrid-ai-coding-architecture-v2_1.md) — the architecture this repo scaffolds.
- [`BuildThisRepoFromArchitecture.md`](./BuildThisRepoFromArchitecture.md) — the implementation plan for the template repo itself.
- [`ProgressBuildingRepo.md`](./ProgressBuildingRepo.md) — execution status of that plan.
