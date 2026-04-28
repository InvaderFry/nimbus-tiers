# Hybrid AI Coding Architecture

**A four-tier design for routing coding tasks across local models, free cloud APIs, and frontier subscriptions to maximize throughput while staying within rate limits.**

---

## Table of Contents

1. [Overview](#overview)
2. [Hardware & Software Foundation](#hardware--software-foundation)
3. [The Four-Tier Architecture](#the-four-tier-architecture)
4. [Tier Specifications](#tier-specifications)
5. [Cloud-Only Mode (No Local Models)](#cloud-only-mode-no-local-models)
6. [The Routing Logic](#the-routing-logic)
7. [The Workflow: Plan → Execute → Review](#the-workflow-plan--execute--review)
8. [Tool Stack Reference](#tool-stack-reference)
9. [Implementation Guide](#implementation-guide)
10. [Cost & Capacity Analysis](#cost--capacity-analysis)
11. [Operational Patterns](#operational-patterns)
12. [Failure Modes & Mitigations](#failure-modes--mitigations)
13. [Future Evolution](#future-evolution)

**Appendices:**
- [A: Task Routing Quick Reference](#appendix-a-task-routing-quick-reference)
- [B: Model Reference](#appendix-b-model-reference)
- [C: Glossary](#appendix-c-glossary)
- [D: Data Classification & Egress Controls](#appendix-d-data-classification--egress-controls)
- [E: Artifact Templates — CONTEXT.md, VERIFY.md](#appendix-e-artifact-templates)
- [F: CURRENT_LIMITS — Provider Facts](#appendix-f-current_limits--provider-facts)
- [G: Metrics & Local Model Eval](#appendix-g-metrics--local-model-eval)

> **A note on numbers throughout this document:** Token counts, tok/s figures, RPM/RPD limits, daily feature throughput, and dollar cost estimates are approximations based on typical workloads and current-as-of-writing data. Provider pricing, model names, and rate limits change frequently — treat all specific figures as ballpark estimates, not commitments. Living provider facts have been moved to [Appendix F](#appendix-f-current_limits--provider-facts), which is intentionally disposable. Track your own usage for two weeks before optimizing against any specific number here.

---

## Overview

### The Problem

Frontier cloud AI produces dramatically better code than what you can run locally on consumer hardware. But Pro-tier subscriptions come with rate limits that frequently throttle real development work. A single complex feature can exhaust your daily quota by mid-afternoon.

### The Insight

Coding work decomposes naturally into three phases with very different intelligence requirements:

- **Planning** — frontier-tier reasoning matters most; quality directly determines downstream success
- **Execution** — mechanical work that follows a clear plan; near-frontier quality is sufficient
- **Review** — frontier-tier reasoning matters again; subtle issues require strong judgment

Local models and free-tier APIs can handle execution at unlimited volume. Cloud subscriptions should be conserved for planning and review. This is the **"expensive brain, cheap hands"** pattern.

### The Solution

A four-tier intelligence routing system:

```
┌─────────────────────────────────────────────────────────────┐
│  Tier 3: Frontier Cloud (Claude Opus, GPT — see App. F)     │
│  Use for: Planning, hard debugging, final review            │
│  Cost: Subscription, rate-limited                           │
└─────────────────────────────────────────────────────────────┘
         ↑ Escalate when quality is critical
┌─────────────────────────────────────────────────────────────┐
│  Tier 2: Free Cloud (Groq large models — see App. F)        │
│  Use for: Better-than-local quality without burning quota   │
│  Cost: Free, daily request and token limits apply           │
└─────────────────────────────────────────────────────────────┘
         ↑ Escalate when local quality insufficient
┌─────────────────────────────────────────────────────────────┐
│  Tier 1: Local Models (Devstral 24B, Qwen2.5-Coder 14B)    │
│  Use for: Bulk execution against clear plans                │
│  Cost: Free, unlimited, private                             │
└─────────────────────────────────────────────────────────────┘
         ↑ Escalate when speed matters more than context
┌─────────────────────────────────────────────────────────────┐
│  Tier 0: Fast Free Cloud (Groq small models — see App. F)   │
│  Use for: Trivial tasks needing instant turnaround          │
│  Cost: Free, generous daily request limits                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Hardware & Software Foundation

### Reference Hardware

This architecture is designed for and validated on:

| Component | Specification |
|---|---|
| GPU | NVIDIA RTX 5080 16GB GDDR7 |
| CPU | AMD Ryzen 7 9850X3D (8 cores, 4.7 GHz base) |
| RAM | 64GB DDR5-6000 |
| Storage | 2TB NVMe SSD |
| OS | Windows 11 + WSL2 |

### VRAM Tiers

VRAM is the hard ceiling for local inference, not raw GPU speed. Use this table to understand what's possible on your hardware:

| VRAM | What fits | Practical capability |
|---|---|---|
| 8GB | 7B–8B models only | Autocomplete, short chat, trivial tasks |
| 16GB | 14B–24B quantized | Full coding execution tier (this build) |
| 24GB | Better long-context, 30B options | Improved multi-file and long-context work |
| 32GB+ | Serious agentic headroom | Multiple models, larger context budgets |
| 48GB+ | 70B-class local experimentation | Near-frontier local quality |

The 16GB VRAM on this build is workable for 14B–24B quantized models. The 64GB system RAM enables MoE CPU offload for models that exceed VRAM.

### Required Software Stack

**Inference backends:**
- **Ollama** — primary local LLM runtime (one-click model management)
- **TabbyAPI** wrapping **ExLlamaV3** — high-speed inference for daily-driver models (~2× faster than Ollama)

**User interfaces:**
- **Open WebUI** — browser-based chat for general use
- **Aider** — terminal-based coding agent (recommended primary)
- **Cline** — VS Code extension for visual agentic coding
- **Continue.dev** — IDE autocomplete

**Cloud subscriptions:**
- Claude Code Pro — primary planning and review
- ChatGPT Pro / Codex (intermittent) — secondary cloud, debugging
- Groq free tier — fallback execution, fast trivial tasks

> Current model names, pricing, and plan details for these services are in [Appendix F](#appendix-f-current_limits--provider-facts).

---

## The Four-Tier Architecture

### Architecture Diagram

```
                    ┌──────────────────────┐
                    │   You (the human)    │
                    │   Arbiter & Reviewer │
                    └──────────┬───────────┘
                               │
              ┌────────────────┴────────────────┐
              │  PLAN.md / TESTS.md / CONTEXT.md │
              │       (Git-tracked state)        │
              └────────────────┬────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   PLANNING    │     │   EXECUTION   │     │    REVIEW     │
│               │     │               │     │               │
│  Claude Code  │     │  Local Aider  │     │  Claude Code  │
│  Opus         │     │  Devstral 24B │     │  Opus         │
│  Plan Mode    │     │  Step-by-step │     │  /review      │
└───────────────┘     └───────┬───────┘     └───────────────┘
                              │
                    ┌─────────┴─────────┐
                    │ Local fails?      │
                    └─────────┬─────────┘
                              ▼
                    ┌───────────────────┐
                    │  Groq Llama 3.3   │
                    │  70B (free)       │
                    └─────────┬─────────┘
                              │
                    ┌─────────┴─────────┐
                    │ Groq fails too?   │
                    └─────────┬─────────┘
                              ▼
                    ┌───────────────────┐
                    │ ChatGPT           │
                    │ (debug specialist)│
                    └───────────────────┘
```

The three markdown files — PLAN.md, TESTS.md, and CONTEXT.md — form the complete handoff contract between phases. See [Appendix E](#appendix-e-artifact-templates) for templates.

### Phase Responsibilities

| Phase | Primary Tool | Model | Why |
|---|---|---|---|
| Planning | Claude Code | Opus (frontier) | Frontier judgment; one-time cost per feature |
| Execution | Aider (WSL) | Devstral 24B (local) | Unlimited volume, no quota burn |
| Fallback Execution | Aider (WSL) | Groq llama-3.3-70b | Better quality when local stalls |
| Debug Escalation | ChatGPT | GPT frontier | Strong at "what's wrong here" |
| Review | Claude Code | Opus (frontier) | Frontier review catches subtle issues |

---

## Tier Specifications

### Tier 0: Fast Free Cloud (Groq Small Models)

**When to use:** Trivial tasks where speed dominates quality concerns.

**Model:** Groq small instant model (see [Appendix F](#appendix-f-current_limits--provider-facts) for current name)

**Characteristics:**
- Very fast output speed (hundreds of tokens/sec — check App. F for current figures)
- Generous RPD limit — suitable for high-frequency trivial use
- Low latency (~50ms time-to-first-token)

**Use cases:**
- Regex generation
- Format conversion (JSON ↔ YAML, etc.)
- Single-line code completion
- Quick syntax questions
- Boilerplate text expansion

**Anti-use cases:**
- Anything requiring code understanding beyond a single function
- Multi-file context
- Privacy-sensitive content

### Tier 1: Local Models (Default Executor)

**When to use:** Default for all coding execution work. Unlimited volume, private, fast enough.

**Primary models:**

| Model | Format | VRAM | Speed | Best For |
|---|---|---|---|---|
| Devstral Small 24B | EXL3 4.0bpw | ~12GB | ~50 tok/s | Agentic coding, multi-file work |
| Qwen2.5-Coder 14B | EXL3 6.0bpw | ~11GB | ~70 tok/s | Single-file work, boilerplate |
| Qwen3 14B Instruct | EXL3 6.0bpw | ~11GB | ~75 tok/s | General reasoning, chat |

> Speed figures are observed on the reference hardware at the quantization levels listed. Your results will vary.

**Backend:** TabbyAPI on `http://localhost:5000`

**Configuration baseline:**
```yaml
max_seq_len: 32768
cache_mode: Q8        # halves KV cache memory
chunk_size: 2048
```

**Use cases:**
- Executing each step of a PLAN.md
- Generating tests from specifications
- Adding docstrings, type hints
- Single-file refactors
- Boilerplate generation (CRUD, configs, scaffolding)
- Privacy-sensitive code work
- High-volume tasks (50+ edits in a session)

**Anti-use cases:**
- Tasks requiring frontier reasoning
- Vague specifications (model fills in wrong assumptions)
- Cross-file architectural changes without clear guidance
- Long autonomous runs without human checkpoints

### Tier 2: Free Cloud Fallback (Groq Large Models)

**When to use:** Local model produced bad output and you don't want to burn Claude quota.

**Primary models** (see [Appendix F](#appendix-f-current_limits--provider-facts) for current rate limits):

| Model | Strengths |
|---|---|
| `llama-3.3-70b-versatile` | Strongest reasoning |
| `openai/gpt-oss-120b` | Best code quality |
| `qwen/qwen3-32b` | Higher RPM for bursty work |

**Critical constraints:**
- TPM ceiling means a large context + long output can exhaust the limit in a single call
- RPD limit means you have a finite number of tasks per day per model
- No SLA — degrades during peak hours
- Privacy: inputs may be temporarily logged by Groq (see [Appendix D](#appendix-d-data-classification--egress-controls))

**Use cases:**
- Local just failed at a task and you need a smarter retry
- Short, well-bounded tasks that fit within TPM limits
- Speed-critical execution
- Tasks where local produces obviously wrong output

**Anti-use cases:**
- Long-context tasks (TPM ceiling will throttle)
- Anything CONFIDENTIAL or SECRET (see Appendix D)
- High-volume bulk work (RPD will exhaust)

### Tier 3: Frontier Cloud (Subscription)

**When to use:** Planning, review, and the rare task where frontier reasoning is mandatory.

**Primary services** (see [Appendix F](#appendix-f-current_limits--provider-facts) for current pricing and limits):

| Service | Strengths |
|---|---|
| Claude Code Pro | Best planning, best code review, agentic coding |
| ChatGPT Pro | Strong debugging, reasoning |
| Codex | PR-style code generation |

**Critical insight:** Independent rate limits across services act as a **capacity multiplier**. When Claude is exhausted, switch to ChatGPT/Codex without waiting for the window to reset.

**Use cases:**
- Initial planning and architecture decisions
- Multi-file refactors
- Debugging non-obvious issues
- Final review pass before merge
- Tasks where wrong implementation is hard to detect by tests

**Anti-use cases:**
- Mechanical execution that has a clear spec
- High-volume repetitive work
- Anything local can do well

---

## Cloud-Only Mode (No Local Models)

This architecture works without Tier 1 (local models). If your hardware can't run local models well, or you simply don't want to manage a local stack, you can skip Tier 1 entirely and operate the same Plan → Execute → Review workflow using only cloud tiers.

### When to skip local models

Choose Cloud-Only Mode if any of these apply:

- **Your GPU has less than 8GB VRAM** — local 14B+ models won't fit at usable quality
- **You don't have a discrete GPU** — CPU-only inference is too slow for agentic work (1-3 tok/s)
- **You're on a laptop with thermal/battery constraints** — local inference will pin the GPU at 100% for hours
- **You don't want the maintenance burden** — drivers, CUDA versions, model updates, debugging Blackwell quirks, etc.
- **Your work is privacy-tolerant** — no sensitive code, no compliance requirements
- **Storage is constrained** — local models need 50-150GB of disk space
- **You're trying the workflow for the first time** — start cloud-only, add local later if value is clear

### The three-tier cloud-only stack

Drop Tier 1 from the architecture. The remaining tiers form a complete workflow:

```
┌─────────────────────────────────────────────────────────────┐
│  Tier 3: Frontier Cloud (Claude Opus, GPT)                  │
│  Use for: Planning, hard debugging, final review            │
└─────────────────────────────────────────────────────────────┘
         ↑ Escalate when quality is critical
┌─────────────────────────────────────────────────────────────┐
│  Tier 2: Free Cloud (Groq large models)                     │
│  Use for: Default execution and fallback                    │
└─────────────────────────────────────────────────────────────┘
         ↑ Escalate when speed matters more than context
┌─────────────────────────────────────────────────────────────┐
│  Tier 0: Fast Free Cloud (Groq small model)                 │
│  Use for: Trivial tasks needing instant turnaround          │
└─────────────────────────────────────────────────────────────┘
```

In Cloud-Only Mode, **Groq's free tier becomes your default executor** instead of local models.

### Adapted routing for Cloud-Only Mode

```
START: New task arrives
  │
  ├─ Is this PLANNING/ARCHITECTURE/REVIEW work?
  │  └─ YES → Tier 3 (Claude Code Opus)
  │
  ├─ Is this PRIVATE/SENSITIVE code?
  │  └─ YES → HARD STOP. Cloud-Only Mode cannot handle this.
  │     Either: switch to local for this task only,
  │           or: escalate the task to a different workflow.
  │     Do NOT issue a warning and proceed — refuse and reroute.
  │
  ├─ Is this trivial (regex, format conversion)?
  │  └─ YES → Tier 0 (Groq small model)
  │
  ├─ Default: try Tier 2 (Groq 70B/120B)
  │  │
  │  ├─ Groq succeeds within rate limits? → DONE
  │  │
  │  ├─ Hit Groq TPM ceiling?
  │  │  └─ Trim context, retry → if still failing, escalate to Tier 3
  │  │
  │  ├─ Hit Groq RPD ceiling?
  │  │  ├─ LOW RISK task → switch to alternate Groq model (independent quota)
  │  │  └─ ALL Groq models exhausted → escalate to Tier 3 or stop new tasks
  │  │
  │  └─ Quality insufficient after retry?
  │     └─ Escalate to Tier 3 (Claude Opus)
```

> **Quota management is not optional in Cloud-Only Mode.** Without local as an unlimited bottom tier, every request consumes a metered resource. When org-level Groq limits are low, stop starting new tasks — do not switch models and hope.

### Cloud-Only Mode tradeoffs

**What you gain:**
- Zero hardware requirements — runs on any machine with a browser and terminal
- Zero setup time — no drivers, no CUDA, no model downloads
- Zero maintenance — no broken builds, no version mismatches
- Faster startup — no warmup, no model loading
- Better quality on hard tasks than local models would have produced anyway

**What you lose:**
- **Privacy** — every request goes to Groq, OpenAI, or Anthropic
- **Unlimited execution** — Groq RPD limits cap your throughput (see Appendix F)
- **Long-context tasks** — Groq TPM ceilings on large models are restrictive
- **Cost predictability when scaling** — heavy users will eventually hit free tier ceilings

### Adapted execution phase for Cloud-Only Mode

Phase 2 (Execute) changes — instead of Aider pointed at local TabbyAPI, point it at Groq:

```bash
# Cloud-Only Mode: Aider with Groq as default executor
aider --model groq/llama-3.3-70b-versatile \
      --read PLAN.md --read TESTS.md --read CONTEXT.md
```

For trivial tasks, swap to the fast small model:
```
/model groq/llama-3.1-8b-instant
```

For better quality on a hard step, swap up:
```
/model groq/openai/gpt-oss-120b
```

When all Groq models are rate-limited, escalate to Claude:
```
/model anthropic/claude-opus-4-6
```

### Quota management in Cloud-Only Mode

- **Trim Aider context aggressively** — every file in `/add` adds to TPM consumption
- **Use `/read-only` instead of `/add`** for PLAN.md, TESTS.md, CONTEXT.md — they don't need editing
- **One step per turn** — large multi-step requests consume more TPM per response
- **Rotate models when one hits its RPD limit** — each model has an independent daily quota
- **Stop starting new tasks when overall org quota is low** — finishing one task cleanly is better than starting three that will stall

### Estimated costs (Cloud-Only)

> All figures are rough estimates. Track your own usage before making spending decisions.

| Usage level | Estimated monthly cost | Notes |
|---|---|---|
| Light (<2 features/day) | ~$20 | Groq free tier handles execution comfortably |
| Moderate (2-4 features/day) | $20-40 | May need ChatGPT Pro for second wind on busy days |
| Heavy (5+ features/day) | $100-200 | Likely need Max tier or paid Groq |
| Full Hybrid | $108-128 + hardware | Local removes the ceiling |

### Migration path: Cloud-Only → Hybrid

1. **Buy/build the hardware** — RTX 4060 Ti 16GB or equivalent is the cheapest viable entry
2. **Install Ollama only** (skip TabbyAPI initially) — one-click setup
3. **Pull Qwen2.5-Coder 14B** as a starting model
4. **Add local as Tier 1 in your Aider config** — keep Groq as fallback
5. **Use local for one feature** — validate quality is acceptable for your codebase
6. **Gradually shift the default** — local for execution, Groq for fallback, Claude for review
7. **Add TabbyAPI/ExLlamaV3 later** — only if you feel the speed limitation

---

## The Routing Logic

### Decision Tree (Memorize These Rules)

```
START: New task arrives
  │
  ├─ Would normal coding be faster? (<10 min, you know the exact edit)
  │  └─ YES → Write it yourself. Don't invoke the orchestration.
  │
  ├─ Is this PLANNING/ARCHITECTURE/REVIEW work?
  │  └─ YES → Tier 3 (Claude Code Opus)
  │
  ├─ Is this trivial (regex, format conversion, single-line)?
  │  └─ YES → Tier 0 (Groq small model)
  │
  ├─ Is this PRIVATE/SENSITIVE code?
  │  └─ YES → Tier 1 (Local) — NO OTHER OPTIONS
  │
  ├─ Default: try Tier 1 (Local)
  │  │
  │  ├─ Local succeeds? → DONE
  │  │
  │  ├─ Local fails once? → Adjust prompt, retry once
  │  │
  │  └─ Local fails twice? → Escalate (see triggers below)
  │     │
  │     ├─ Is task SHORT (fits within Groq TPM)?
  │     │  └─ YES + not CONFIDENTIAL → Tier 2 (Groq 70B/120B)
  │     │
  │     ├─ Is task DEBUGGING ("why doesn't this work")?
  │     │  └─ YES → ChatGPT
  │     │
  │     └─ Otherwise → Tier 3 (Claude Opus)
```

### When to escalate — objective triggers

Don't rely on gut feel. Escalate when any of these are true:

- The same test fails after 2 repair attempts by the current model
- The model edits files outside the list specified in PLAN.md
- The diff is more than 2× the line count expected in the plan
- The model invents APIs, imports, or dependencies not in the codebase
- The model changes public behavior not listed in PLAN.md
- You cannot explain the diff in 5 minutes

These are operating conditions, not judgment calls.

### When NOT to use the orchestration

Use normal coding if:
- The change is under 10 minutes and you already know the exact edit
- Generated code would take longer to review than it would take to write
- The task is mostly product judgment, not implementation
- You're in an unfamiliar codebase where you need to understand every line anyway

The workflow is overhead. Overhead is only worth it when the output value exceeds the orchestration cost.

### The 80/20 Heuristic

In a typical coding day, work distributes roughly:

- **~70% of work** → Tier 1 (local execution against a clear plan)
- **~15% of work** → Tier 3 (planning + review)
- **~10% of work** → Tier 2 (fallback when local stalls)
- **~5% of work** → Tier 0 (trivial speed-critical tasks)

If you're routinely escalating more than 30% to cloud, your plans aren't specific enough — invest more time in the planning phase.

---

## The Workflow: Plan → Execute → Review

The three phases handoff through three markdown files. These form the complete execution contract:

- **PLAN.md** — what to do, step by step
- **TESTS.md** — what passing looks like
- **CONTEXT.md** — constraints the executor must not violate

See [Appendix E](#appendix-e-artifact-templates) for templates for all three.

### Phase 1: Planning (Claude Code)

**Duration:** roughly 15-30 minutes *(estimate, varies by task complexity)*
**Quota cost:** roughly 50K tokens *(estimate)*
**Output:** `PLAN.md`, `TESTS.md`, and `CONTEXT.md` saved to repo

**Process:**

1. Open Claude Code in repo root
2. Enter plan mode (Shift+Tab)
3. Provide task description and point at relevant files
4. Iterate 1-2 times for refinement
5. Save all three output files

**Plan prompt template:**

```
Don't write code yet. Read the relevant files in this codebase,
understand the architecture, and produce a numbered implementation
plan for [feature/task].

For each step, specify:
1. Which file(s) to modify
2. What change to make
3. What the change should accomplish
4. Edge cases to handle
5. Tests to write

Be specific enough that a less capable engineer could execute
each step without re-reading the codebase.

Also produce:
- TESTS.md listing what tests should exist when this is complete,
  with brief descriptions of each test's purpose.
- CONTEXT.md capturing invariants, public contracts, naming
  conventions, and do-not-touch areas the executor must respect.
  (See CONTEXT.md template in Appendix E.)
```

**Quality checklist for the plan:**
- ☐ Each step modifies a clearly specified file
- ☐ No step requires reading more than 2-3 other files
- ☐ Each step takes <50 lines of code to execute
- ☐ Edge cases are listed, not implied
- ☐ Acceptance criteria are testable
- ☐ CONTEXT.md lists at least: key invariants, public API contracts, do-not-change areas

### Phase 2: Execution (Local Aider)

**Duration:** roughly 1-3 hours *(estimate, scales with feature size)*
**Quota cost:** Zero (no cloud calls in pure local execution)
**Output:** Series of git commits, one per step

**Process:**

1. Open WSL terminal in repo root
2. Launch Aider with all three phase files in read-only context:

```bash
aider --model openai/devstral-small-24b \
      --openai-api-base http://localhost:5000/v1 \
      --openai-api-key notneeded \
      --read PLAN.md --read TESTS.md --read CONTEXT.md
```

3. Execute steps one at a time:

```
Execute step 1 of PLAN.md. Implement only that step.
Do not modify files not listed in that step.
```

4. Verify after each step: run tests, inspect diff, approve commit
5. Continue through all steps

**Critical rules:**
- One step per turn (prevents Devstral going off-script)
- Don't proceed if a step's tests fail
- If local fails twice on the same step, escalate using the objective triggers above

**Escalation within Aider session:**

```
# Mid-session model swap when local stalls
/model groq/llama-3.3-70b-versatile

# After successful step, swap back
/model openai/devstral-small-24b
```

**Auto-commit modes:**

Use the appropriate mode for the risk level of the work. In `~/.aider.conf.yml` or the repo's `.aider.conf.yml`:

```yaml
# Safe mode — routine steps, low-risk changes
auto-commits: true
auto-test: true
test-cmd: pytest -x --no-header

# High-risk mode — auth, billing, data migrations, large refactors
# auto-commits: false   ← uncomment for these sessions
auto-test: true
test-cmd: pytest -x --no-header
```

When `auto-commits` is false, Aider stages the changes and waits for you to review the diff before committing. For security-sensitive or large-impact changes, reviewing the diff before it hits git history is worth the extra step.

### Phase 3: Review (Claude Code)

**Duration:** roughly 15-30 minutes *(estimate)*
**Quota cost:** roughly 30K tokens *(estimate)*
**Output:** Fix list or approval

**Final approval requires all three gates:**

1. **CI green** — tests, typecheck, lint, format, all checks in VERIFY.md pass
2. **AI review issues resolved or explicitly waived** — nothing outstanding from the review prompt
3. **Human review of diff and behavior** — you can explain every material change

For auth, payment, data migration, or security-impacting changes: require a second human reviewer or a domain-specific checklist before merge.

**Process:**

1. Run your repo's VERIFY.md checklist (see [Appendix E](#appendix-e-artifact-templates))
2. Reopen Claude Code in repo
3. Run review prompt against the diff
4. Apply any fixes locally (Phase 2 mini-loop)
5. Optionally one more review pass
6. When all three gates are satisfied: final commit and merge

**Review prompt template:**

```
Review the diff between [base-commit] and HEAD against PLAN.md,
TESTS.md, and CONTEXT.md. Check for:

1. Did each step get implemented as specified in PLAN.md?
2. Are all tests from TESTS.md present and passing?
3. Were all invariants and constraints in CONTEXT.md respected?
4. Bugs, edge cases, security issues
5. Style/consistency with the rest of the codebase
6. Performance regressions
7. Any deviations from the plan that need justification

Produce a numbered list of required fixes, ordered by severity.
If no fixes needed, say "APPROVED" and provide a one-paragraph
summary of the changes for the commit message.
```

### State Persistence

The seam between phases is the filesystem, not API state:

```
your-repo/
├── PLAN.md           # Phase 1 output, Phase 2 + 3 input
├── TESTS.md          # Phase 1 output, Phase 2 + 3 input
├── CONTEXT.md        # Phase 1 output, Phase 2 + 3 input
├── VERIFY.md         # Repo-level verification checklist
├── plans/            # Archive of completed plans (reusable patterns)
│   ├── README.md     # Index of past plans
│   ├── 2026-04-auth.md
│   └── 2026-04-billing.md
└── src/
    └── ...
```

**What to commit vs. gitignore:**

```
# Commit these — they document the work and inform future sessions:
CONTEXT.md
VERIFY.md
plans/

# Optionally gitignore these per-task working files:
PLAN.md
TESTS.md
.aider.tags.cache.v3/
```

Raw prompts, cloud transcripts, stack traces with customer data, and debugging dumps should never be committed. If your PLAN.md contains sensitive context (production data, customer info, proprietary details), gitignore it.

This makes the workflow:
- **Debuggable** — every input and output is a text file
- **Resumable** — interrupt anywhere, restart from last commit
- **Reviewable** — plan and context live with the code
- **Reusable** — past plans inform future similar features

---

## Tool Stack Reference

### Backend Services (Always Running)

**Ollama** — `http://localhost:11434`
- Embeddings (bge-m3 for RAG)
- Reranker (bge-reranker-v2-m3)
- Vision models (Qwen2.5-VL 7B, Gemma 3 vision)
- Small/experimental models
- MoE-with-CPU-offload models

**TabbyAPI** — `http://localhost:5000`
- Daily-driver chat model (Qwen3 14B)
- Coding model (Qwen2.5-Coder 14B or Devstral 24B)
- High-throughput inference for active development

### User-Facing Tools

| Tool | When to Use | Backend |
|---|---|---|
| **Open WebUI** | Browser chat, document upload, MCP tools | Both |
| **Aider** (WSL) | Terminal-based coding execution | TabbyAPI |
| **Cline** (VS Code) | Visual agentic coding with approvals | TabbyAPI |
| **Continue.dev** (VS Code) | Inline autocomplete | Ollama (smaller model) |
| **AnythingLLM** | Persistent document workspaces | Ollama |
| **n8n** (Docker) | Scheduled/triggered automations | Ollama |
| **Goose** (CLI) | "Do this for me" tasks with MCP | Either |

### Tool Selection Decision Tree

```
What are you doing right now?
│
├─ In VS Code with code open?
│  ├─ Want autocomplete? → Continue.dev
│  └─ Multi-step coding task? → Cline
│
├─ In a terminal?
│  ├─ Coding with git? → Aider
│  └─ General agent task? → Goose
│
├─ Need to chat with documents?
│  ├─ One-off? → Open WebUI with file upload
│  └─ Persistent collection? → AnythingLLM
│
├─ Building automation?
│  └─ → n8n
│
└─ Default → Open WebUI
```

---

## Implementation Guide

### Pick Your Setup Path First

Before working through the checklist, decide which path applies to you:

- **Path A: Cloud-Only Mode** — skip all local model setup, use Groq + Claude/ChatGPT subscriptions only. Fastest to set up, no hardware requirements.
- **Path B: Light Local (Ollama only)** — add a single local-model runtime. Lower setup burden than full hybrid. Good middle ground.
- **Path C: Full Hybrid (Ollama + TabbyAPI/ExLlamaV3)** — maximum local capability and speed. Most setup work.

### Initial Setup Checklist

**Prerequisites (all paths):**
- ☐ Git installed
- ☐ Python 3.11+ available
- ☐ A terminal you're comfortable in (WSL2 on Windows, native on Linux/Mac)

**Prerequisites (Path B and C only — local hardware):**
- ☐ NVIDIA GPU with at least 8GB VRAM (16GB+ recommended — see VRAM tier table)
- ☐ NVIDIA driver 572.16+ with CUDA 12.8+ *(version requirements may shift over time)*
- ☐ Visual Studio Build Tools with C++ workload (Windows)
- ☐ At least 100GB free disk space for models

**Path A: Cloud-Only Mode setup:**
- ☐ Claude Code installed and authenticated (`claude auth`)
- ☐ ChatGPT Pro subscription active (optional, for second wind)
- ☐ Groq account created at console.groq.com
- ☐ `GROQ_API_KEY` set in shell environment
- ☐ Aider installed: `pip install aider-install && aider-install`
- ☐ Aider configured (see config section below)
- ☐ Tested: `aider --model groq/llama-3.3-70b-versatile` opens a working session
- ☐ Data classification reviewed — confirm all planned work is PUBLIC or INTERNAL (see Appendix D)

**Path B: Light Local setup (adds to Path A):**
- ☐ Ollama installed from ollama.com, running on port 11434
- ☐ Set `OLLAMA_FLASH_ATTENTION=1` env var
- ☐ Set `OLLAMA_KV_CACHE_TYPE=q8_0` env var
- ☐ Move models off system drive: set `OLLAMA_MODELS` to a path with space
- ☐ Pull a coding model: `ollama pull qwen2.5-coder:14b`
- ☐ Pull embeddings: `ollama pull bge-m3`
- ☐ Tested: `ollama run qwen2.5-coder:14b` produces output
- ☐ Aider tested with local: `aider --model openai/qwen2.5-coder:14b --openai-api-base http://localhost:11434/v1`

**Path C: Full Hybrid setup (adds to Path B):**
- ☐ TabbyAPI cloned to a working directory
- ☐ Python venv created and activated for TabbyAPI
- ☐ PyTorch with CUDA 12.8 installed in venv
- ☐ TabbyAPI's `start.py` completed (Flash Attention compiled successfully)
- ☐ EXL3 models downloaded from Hugging Face (turboderp's quants)
- ☐ TabbyAPI `config.yml` configured (model path, max_seq_len, Q8 cache)
- ☐ TabbyAPI launches without errors at port 5000
- ☐ `nvidia-smi` shows expected VRAM usage with model loaded
- ☐ Aider tested against TabbyAPI: `aider --openai-api-base http://localhost:5000/v1`

**Optional UI tools (any path):**
- ☐ Open WebUI (Docker easiest): browser-based chat for general use
- ☐ Cline VS Code extension: visual agentic coding
- ☐ Continue.dev VS Code extension: inline autocomplete
- ☐ AnythingLLM desktop: persistent document workspaces
- ☐ n8n (Docker): scheduled automations

**Per-repo setup (any path):**
- ☐ Create `CONTEXT.md` for the repo (see Appendix E template)
- ☐ Create `VERIFY.md` for the repo (see Appendix E template)
- ☐ Add `PLAN.md` and `TESTS.md` to `.gitignore` (or commit them — your call)

### Aider Configuration

Create `~/.aider.conf.yml` in WSL. The exact YAML format and supported keys can change between Aider versions — verify against `aider --help` and the [Aider config docs](https://aider.chat/docs/config/aider_conf.html) before relying on advanced options.

**Hybrid mode (with local TabbyAPI):**

```yaml
# Default to local model via TabbyAPI's OpenAI-compatible endpoint
model: openai/devstral-small-24b
openai-api-base: http://localhost:5000/v1
openai-api-key: notneeded

# Safe mode default — change per-repo for high-risk work
auto-commits: true
auto-test: true
test-cmd: pytest -x --no-header
```

**Cloud-Only Mode:**

```yaml
# Default to Groq's strongest free model
model: groq/llama-3.3-70b-versatile
# Set GROQ_API_KEY in your shell environment

auto-commits: true
auto-test: true
test-cmd: pytest -x --no-header
```

**High-risk repo override** (place in repo-root `.aider.conf.yml` to override global):

```yaml
# Override for repos with auth, billing, migrations, or security-sensitive code
auto-commits: false
auto-test: true
test-cmd: ./scripts/verify.sh   # your VERIFY.md quick checks
```

**Mid-session model switching:** Aider supports the `/model <model-name>` command in any session. The model strings used throughout this doc follow Aider's litellm-style naming (e.g., `groq/llama-3.3-70b-versatile`, `anthropic/claude-opus-4-6`).

### Quick Commands Cheat Sheet

```bash
# Start Aider with all three phase files in read-only context
aider --read PLAN.md --read TESTS.md --read CONTEXT.md

# Switch to Groq fallback mid-session
/model groq/llama-3.3-70b-versatile

# Switch back to local
/model openai/devstral-small-24b

# Add a file to context (makes it editable)
/add src/new_feature.py

# Drop a file from context (when context gets crowded)
/drop src/legacy.py

# Read a file in (read-only, lower context cost than /add)
/read-only docs/architecture.md

# Run a shell command and add output to context
/run pytest -x

# Show current diff of edits
/diff

# Reset context (clear the chat history but keep files)
/clear

# Show token usage so far
/tokens

# Get help
/help
```

Aider's full slash command list is available via `/help` in any session. Commands evolve between releases.

---

## Cost & Capacity Analysis

### Monthly Cost Comparison

> **All numbers below are estimates** based on typical workloads as of writing. Subscription pricing and rate limits change frequently. Track your actual usage for a month before making decisions based on these figures. See Appendix F for current provider pricing.

**Hybrid architecture — estimates:**
- Claude Code Pro + ChatGPT Pro (intermittent): ~$20-40/month in subscriptions
- Hardware amortization: ~$78/month *(based on ~$2,800 build over 3 years)*
- Electricity: ~$10/month *(varies by GPU usage and local rates)*
- Groq: $0 (free tier)
- **Total: roughly $108-128/month**
- Effective capacity: roughly 3-5 features/day with less rate limit anxiety

**Cloud-Only Mode — estimates:**
- Claude Code Pro + optional ChatGPT Pro: $20-40/month
- **Total: $20-40/month**
- Effective capacity: roughly 1-3 features/day (gated by Groq RPD ceiling)

### Quota Usage Per Feature

> **All token counts below are estimates** that vary significantly by codebase size, prompt style, and feature complexity.

**Hybrid execution — estimates:**
- Plan: ~50K Claude tokens
- Execute: 0 Claude tokens (all local)
- Optional Groq fallback: 0 Claude tokens
- Review: ~30K Claude tokens
- Optional fix loop: ~30K Claude tokens
- **Total: roughly 80-110K Claude tokens per feature**

**Cloud-only execution — estimates:**
- Plan: ~50K tokens
- Execute: ~200K-500K tokens (file reads + edits over 30+ minutes)
- Review: ~30K tokens
- **Total: roughly 280K-580K Claude tokens per feature**

**Capacity multiplier: estimated 3-5× more features per day on the same Claude quota**

### When the Architecture Doesn't Pay Off

Be honest about diminishing returns. Skip this architecture if:

- You ship <2 features/week (orchestration overhead exceeds savings)
- Your Pro plan is rarely rate-limited (you don't have the problem)
- You work primarily in unfamiliar codebases (cloud context throughout is correct)
- The change is under 10 minutes and you know exactly what to write

For a hobbyist who codes 3 hours/week, just use Claude Code straight. The hybrid pattern is for people who code 15+ hours/week and feel the rate limits.

---

## Operational Patterns

### Pattern 1: The Standard Day

```
9:00 AM — Open Claude Code, plan today's feature (PLAN.md + TESTS.md + CONTEXT.md)
9:30 AM — Switch to WSL, launch Aider
9:30 AM–12:00 PM — Execute Steps 1-5 with local Devstral
12:00 PM — Lunch
1:00 PM — Continue Steps 6-10
3:00 PM — Run VERIFY.md checklist
3:15 PM — Open Claude Code, review the diff
3:30 PM — Apply 3 fixes locally
3:45 PM — Final review pass, all three gates satisfied, merge
4:00 PM — Plan tomorrow's feature in Claude Code
```

**Quota usage:** roughly 150K Claude tokens *(estimate, ~15-20% of typical daily Pro quota)*
**Output:** One complete feature shipped + tomorrow's plan ready

### Pattern 2: Parallel Multi-Feature Day

When you have multiple independent features to work on — **use Git worktrees**. Running two Aider sessions in the same repo risks competing writes to PLAN.md, dirty working tree state, and interleaved commits that are hard to review or revert.

**Setup:**

```bash
# Each feature gets its own worktree, branch, and clean state
git worktree add ../repo-feature-a -b feature/a
git worktree add ../repo-feature-b -b feature/b
```

Each worktree gets its own PLAN.md, TESTS.md, CONTEXT.md, Aider session, and test state. They don't share working tree state.

**Workflow:**

```
Morning: Plan all features in one Claude Code session
         (saves token overhead vs separate planning sessions)
         Copy PLAN.md / TESTS.md to each worktree

Mid-day: Execute Feature A in ../repo-feature-a (terminal 1)
         Execute Feature B in ../repo-feature-b (terminal 2)
         Each Aider session is fully isolated

Afternoon: Review all together in one Claude Code session
           Run VERIFY.md in each worktree before review

Evening: Apply all fixes, merge each branch cleanly.
```

**Why this works:** Planning overhead amortizes across features. One review session is cheaper than three. Worktrees prevent the parallel sessions from corrupting each other.

### Pattern 3: Cheap Parallel Exploration

When stuck on a design question:

1. Local Devstral generates 3-5 candidate implementations (10 min, $0)
2. Paste all candidates into Claude Code with this prompt:

```
Compare these candidate implementations for [my constraints].
Score each one on:
- Correctness and edge case handling
- Minimality (does it add unnecessary complexity?)
- Testability
- Rollback safety if something goes wrong
- Consistency with the existing codebase style

Pick the best one and explain why. If none are acceptable, say so
and describe what a better approach would look like.
```

3. Claude judges with frontier reasoning
4. Local executes the chosen one

This converts cloud from "producer of one answer" to "judge of many cheap answers." Often produces better results because cloud sees the tradeoffs concretely. Allowing "none of these are acceptable" as a valid outcome prevents the judge from forcing a choice between bad options.

### Pattern 4: The Quota-Stretching Workday

When you've already half-burned Claude quota and need to keep going:

```
First exhaustion (Claude rate limit hit):
  → Switch to ChatGPT/Codex for review
  → Continue local execution unchanged

Second exhaustion (ChatGPT also hit):
  → Use Groq llama-3.3-70b for fallback execution
  → Defer non-critical reviews to next day

Total exhaustion (everything cloud is gated):
  → Pure local mode for execution
  → Generate review checklists locally for self-review
  → Ship without cloud final pass (acceptable for low-stakes work)
```

The key insight: **rate limits across providers are independent**. Three subscription services + Groq free tier = ~4× the headroom of any single service.

### Pattern 5: The Privacy-Required Workflow

For sensitive code (work, NDA'd projects, secrets):

```
All phases run local. No cloud calls anywhere.
Verify data classification first — see Appendix D.

Plan: Open WebUI with Qwen3 14B, manually craft PLAN.md
Execute: Aider with Devstral 24B + read CONTEXT.md
Review: Aider with /review or manual diff review + VERIFY.md
```

This is genuinely useful for the 10-20% of work where compliance matters. The architecture cleanly degrades to local-only without breaking.

---

## Failure Modes & Mitigations

### Failure 1: The Plan Was Too Vague

**Symptom:** Local Devstral produces technically-correct but architecturally-wrong code.

**Cause:** Frontier models filled in implicit context that local can't.

**Mitigation:**
- Force planning prompt to be obnoxiously specific
- Require pseudo-code level detail
- Break steps that take >50 lines into sub-steps
- Include file paths, function signatures, return types explicitly
- Use CONTEXT.md to capture invariants the planner knows but didn't state

### Failure 2: Local Goes Off-Script

**Symptom:** Devstral "improves" things you didn't ask for, skips steps, refactors unrelated code.

**Cause:** Model autonomy overriding the plan.

**Mitigation:**
- One step per turn, always
- Explicit instruction: "Implement only step N. Do not modify files not listed in that step."
- Review diff before approving
- Use escalation trigger: model edits files outside the allowed list → escalate immediately

### Failure 3: Tool-Use Chains Break

**Symptom:** Model makes 5 perfect tool calls then a malformed one.

**Cause:** 24B models have lower tool-call reliability than frontier.

**Mitigation:**
- Keep individual steps to 1-3 tool calls each
- Save long autonomous runs for cloud
- Add retry-with-clarification for failed calls
- Use Aider's auto-test feature to catch errors early

### Failure 4: Context Pollution Between Phases

**Symptom:** Local execution doesn't have the context cloud planning had.

**Cause:** PLAN.md doesn't capture all the implicit understanding.

**Mitigation:**
- This is what CONTEXT.md is for — use it
- CONTEXT.md must include: key invariants, public API contracts, naming conventions, do-not-change areas
- Reference "gold standard files" that exemplify the codebase style
- Use Aider's `--read` flag for reference files (read-only, low context cost)

### Failure 5: Review Surfaces Plan-Level Issues

**Symptom:** Cloud review finds problems that should have been caught in planning.

**Cause:** Plan was incomplete.

**Mitigation:**
- Spend 20% more time on planning
- Add explicit "edge cases" and "what could go wrong" sections to PLAN.md
- After review iterations, update plan template with new patterns

### Failure 6: Loops Never Converge

**Symptom:** Cloud review → local fixes → cloud finds new issues → repeat indefinitely.

**Cause:** The plan was fundamentally wrong.

**Rule of thumb:** If you're on iteration 4, **stop. Reset.** Re-plan from scratch with what you've learned.

### Failure 7: Groq TPM Ceiling Hits Mid-Task

**Symptom:** "Rate limit exceeded" mid-Aider-session when escalating to Groq.

**Cause:** Combined input+output exceeds the per-minute token limit.

**Mitigation:**
- Trim Aider context (`/drop` unnecessary files) before escalating
- Use a higher-RPM Groq model for short tasks needing burst capacity (see Appendix F)
- If task truly needs long context, escalate to Tier 3 instead
- If all Groq models are exhausted for the day, stop starting new Groq tasks — do not chase limits across models hoping one has headroom

### Failure 8: The Local Stack Stops Working

**Symptom:** TabbyAPI won't start, model load fails, gibberish output on Blackwell.

**Common causes & fixes:**

| Issue | Fix |
|---|---|
| TabbyAPI won't launch | Check CUDA 12.8 install, update PyTorch wheel |
| Model loads but slow tok/s | Verify Flash Attention enabled in logs |
| Gibberish on Q4_K_M GGUF | Add `-DGGML_CUDA_FORCE_CUBLAS=on` to llama.cpp build |
| OOM at expected context | Drop to lower bpw or shorter `max_seq_len` |
| Can't find model | Check `OLLAMA_MODELS` env var, verify path |

**Always have a fallback:** Keep tuned Ollama running alongside TabbyAPI. If TabbyAPI breaks, point Aider at Ollama (`http://localhost:11434/v1`) with `qwen2.5-coder:14b` and keep working.

---

## Future Evolution

### Near-Term Watchlist (Mid-2026)

These developments could meaningfully change the architecture:

**Local model improvements:**
- Qwen3.5-Coder series — expected to close 5-10 points on SWE-Bench
- DeepSeek V4-Lite — possibly fits in 16GB at 4bpw
- BitNet-distilled models — could enable 70B-class quality on consumer hardware

**Tooling:**
- Open Code (Sourcegraph) — possibly first OSS Claude Code with first-class local support
- Aider's autonomous mode improvements
- ExLlamaV3.5 with FP4 native support on Blackwell

**Cloud landscape:**
- Anthropic Sonnet at lower price point
- DeepSeek V4-Flash at aggressive pricing — disrupts the "free local" calculus
- Llama 5 / open-weight frontier model — would change everything

### When to Re-Evaluate the Architecture

Trigger a re-evaluation if any of these become true:

- ☐ A local 27B+ model matches Claude Sonnet on Aider Polyglot benchmark
- ☐ A capable model ships consistent <$0.50/M tokens — local cost advantage erodes
- ☐ Anthropic releases a higher-limit tier at a price that makes sense for your usage
- ☐ Your work shifts to <5 hours/week (overhead exceeds value)
- ☐ Your work shifts to >40 hours/week (consider Max tier instead)

### Graduation Paths

**From Cloud-Only Mode:**
- **Cloud-Only → Light Local (Path B)**: Add Ollama + a 16GB GPU when you're hitting Groq RPD limits 3+ days/week.
- **Cloud-Only → Higher subscription tier**: Skip hardware, upgrade to a Max tier if you'd rather pay than maintain a local stack.

**From Hybrid:**
- **Hardware upgrade**: Add second RTX 5080 or single RTX 5090 → 32GB+ VRAM. Enables 70B local models. Cost: roughly $1,500-2,500. Justifies if local-execution savings exceed ~$150/month value.
- **Subscription upgrade**: Max tier effectively removes Claude rate limits. Justifies if hybrid orchestration overhead annoys you more than the price difference.
- **API-direct workflow**: Drop Pro subscription, pay per token. Worth it only at very specific usage patterns. Cost-control discipline required.

> **All cost figures in this section are estimates** that depend heavily on usage patterns and provider pricing changes.

### What Won't Change

The architectural pattern itself is durable:

- **Plan / Execute / Review decomposition** — fundamental to coding work
- **Frontier-for-judgment, local-for-volume** — economic reality
- **Markdown files as state** — language-agnostic, simple, debuggable
- **Tool-agnostic seams** — model swap doesn't require workflow rewrite

Specific tools and models will rotate, but if you internalize the pattern, you can re-implement it on whatever stack exists in 2027 or 2028.

---

## Appendix A: Task Routing Quick Reference

| Task Type | Tool | Model |
|---|---|---|
| Autocomplete | Continue.dev | Qwen2.5-Coder 7B (Ollama) |
| Explain code | Continue.dev / Open WebUI | Qwen2.5-Coder 14B |
| Write a regex | Open WebUI / Groq | Any |
| Generate boilerplate | Cline / Aider | Qwen2.5-Coder 14B |
| Write unit tests | Aider | Qwen2.5-Coder 14B |
| Single-file refactor | Aider | Devstral 24B |
| Multi-file refactor | Claude Code | Opus (frontier) |
| Code review (small) | Aider `/review` | Devstral 24B |
| Code review (large) | Claude Code | Opus / Sonnet |
| Architecture design | Claude Code | Opus (frontier) |
| Hard debugging | ChatGPT | GPT frontier |
| Plan creation | Claude Code | Opus plan mode |
| Plan execution | Aider | Devstral 24B |
| Final review | Claude Code | Opus (frontier) |
| Documentation | Cline / Aider | Qwen2.5-Coder 14B |
| SQL generation | Open WebUI | Qwen2.5-Coder 14B |
| Vision tasks | Open WebUI / Claude.ai | Local Gemma 3 / Cloud Opus |

---

## Appendix B: Model Reference

> Rate limits and speed figures below are observed values, not guarantees. Provider limits change without notice. Check [Appendix F](#appendix-f-current_limits--provider-facts) for the dated snapshot and links to current docs.

### Local Models (TabbyAPI/Ollama)

| Model | Size | VRAM | Best For |
|---|---|---|---|
| Qwen3 14B Instruct | 14B | 11GB @ Q6 | Daily chat, reasoning |
| Qwen2.5-Coder 14B | 14B | 11GB @ Q6 | Coding execution |
| Devstral Small 24B | 24B | 12GB @ Q4 | Agentic coding |
| Qwen3-Coder-30B-A3B | 30B MoE | 16GB w/offload | Long-context coding |
| Phi-4-Reasoning-Plus | 14B | 11GB | Math, logic |
| gpt-oss-20B | 20B | 13GB MXFP4 | Fast tool use |
| Gemma 3 12B Vision | 12B | 9GB | Multimodal |
| bge-m3 | 0.6B | 2GB | Embeddings |

### Free Cloud (Groq)

| Model | RPM | TPM | Best For |
|---|---|---|---|
| llama-3.1-8b-instant | 30 | 6K | Trivial fast tasks |
| llama-3.3-70b-versatile | 30 | 12K | Smart fallback |
| qwen3-32b | 60 | 6K | Bursty short work |
| openai/gpt-oss-120b | 30 | 8K | Best free quality |
| llama-4-scout-17b-16e | 30 | 30K | Long context free |

*RPD limits (requests per day) apply at the org level and change over time. Check console.groq.com for current limits.*

### Subscription Cloud

| Service | Best For |
|---|---|
| Claude Code Pro | Planning, review, agentic |
| Claude.ai | Chat, file analysis |
| ChatGPT Pro | Reasoning, debugging |
| Codex | PR-style generation |

*Current model names and plan pricing are in Appendix F.*

---

## Appendix C: Glossary

| Term | Definition |
|---|---|
| **bpw** | Bits per weight — quantization granularity for EXL3 format |
| **CONTEXT.md** | The third phase handoff artifact — captures invariants, contracts, and do-not-change areas |
| **EXL3** | ExLlamaV3 quantization format, NVIDIA-only, faster than GGUF |
| **GGUF** | llama.cpp quantization format, broader compatibility |
| **KV cache** | Key-value cache holding context state, major VRAM consumer |
| **MoE** | Mixture of Experts — model with sparse activation |
| **MXFP4** | 4-bit microscaling float, native to gpt-oss models |
| **PLAN.md** | The contract between Phase 1 (planning) and Phase 2 (execution) |
| **Q4_K_M / Q6_K** | GGUF quantization levels, higher = more quality |
| **RPM / RPD** | Requests per minute / per day (rate limit units) |
| **TESTS.md** | Specifies what passing looks like for a given task |
| **TPM / TPD** | Tokens per minute / per day |
| **Tool use** | Model's ability to call external functions reliably |
| **VERIFY.md** | Repo-level checklist of checks required before commit and before merge |
| **Worktree** | Git feature that checks out a branch into a separate directory — enables isolated parallel Aider sessions |
| **WSL2** | Windows Subsystem for Linux v2 — runs Ubuntu inside Windows |

---

## Appendix D: Data Classification & Egress Controls

Privacy is only meaningful if it's enforced by the system, not relied on as a human rule. This appendix defines which data can go where and how to enforce it.

### Classification Tiers

| Tier | Definition | Allowed destinations |
|---|---|---|
| **PUBLIC** | Open source, public docs, toy projects, nothing sensitive | Any tier — local, Groq, Claude, ChatGPT |
| **INTERNAL** | Work code with no PII, secrets, or compliance requirements | Local + approved cloud (Claude, ChatGPT) only; Groq only if Zero Data Retention is confirmed |
| **CONFIDENTIAL** | Proprietary business logic, unreleased IP, private customer data | Local only. No cloud escalation without explicit approval. |
| **SECRET / REGULATED** | Secrets, credentials, PII, HIPAA/PCI-adjacent data | Local only. No cloud, no telemetry upload of any kind. |

When in doubt, classify up, not down.

### What counts as sensitive

Common things that accidentally land in cloud requests:

- `.env` files and their contents
- Stack traces that include database connection strings
- API keys or tokens in code comments
- Customer-identifying fields in test fixtures
- Internal service names, hostnames, or IP addresses
- Unreleased feature names or business plans in issue context
- Private GitHub issue content pasted into planning prompts

### Enforcement mechanisms

**File-level controls:**
```
# .aiderignore — prevent Aider from reading these files
.env
.env.*
secrets/
**/credentials.*
**/api_keys.*
```

```
# .gitignore — prevent accidental commit
.env
.env.*
secrets/
PLAN.md          # if it might contain sensitive context
```

**Preflight check before cloud escalation:**

Before switching `/model` to any cloud provider, answer:
- Does the current Aider context include any CONFIDENTIAL or SECRET files?
- Does PLAN.md contain any internal hostnames, credentials, or customer data?
- Did the last `/run` output include a stack trace with connection strings?

If yes to any of these: `/drop` the sensitive files, scrub PLAN.md, then escalate.

**Secret scanning:**

```bash
# Quick check before any cloud escalation
grep -r "API_KEY\|SECRET\|PASSWORD\|TOKEN" --include="*.md" .
```

Consider adding `detect-secrets` or `trufflehog` as a pre-commit hook for repos that handle credentials.

### Cloud escalation checklist

Before escalating to any cloud tier for INTERNAL work:

- ☐ No `.env` or credentials files in Aider context
- ☐ PLAN.md reviewed — no internal hostnames, keys, or PII
- ☐ Last test output reviewed — no secrets in stack traces
- ☐ Groq ZDR status confirmed if using Groq for INTERNAL work

### Groq data retention

As of this writing, Groq's default policy does not retain customer data long-term, but inputs and outputs may be temporarily logged for reliability and abuse monitoring. Zero Data Retention (ZDR) controls exist but require explicit activation. For INTERNAL work on Groq, confirm ZDR status before use. For CONFIDENTIAL or SECRET work: local only, no exceptions.

---

## Appendix E: Artifact Templates

These are the three files that form the handoff contract between phases. Keep them in your repo root during active work.

### PLAN.md template

```markdown
# PLAN.md — [Feature/Task Name]

**Date:** YYYY-MM-DD
**Branch:** feature/name
**Planner:** Claude Code Opus
**Estimated steps:** N

## Objective

[One paragraph: what this change does and why.]

## Steps

### Step 1: [What changes]
**File(s):** `src/path/to/file.py`
**Change:** [Specific description]
**Purpose:** [Why this step is needed]
**Edge cases:** [What could go wrong]
**Tests:** [What to verify after this step]

### Step 2: [What changes]
...

## Edge Cases & Risks

- [Known risk 1]
- [Known risk 2]

## Out of Scope

- [What this change explicitly does NOT do]
```

### TESTS.md template

```markdown
# TESTS.md — [Feature/Task Name]

## Required on completion

### Unit tests
- [ ] `test_[name]` — [What it verifies]
- [ ] `test_[name]_edge_case` — [What edge case]

### Integration tests
- [ ] `test_[flow]` — [What end-to-end behavior]

### Regression
- [ ] Existing tests still pass (run full suite)

## Acceptance criteria

- [ ] [Observable behavior 1]
- [ ] [Observable behavior 2]

## What CI must pass before merge

- [ ] Unit tests
- [ ] Type check
- [ ] Lint
- [ ] [Other repo-specific checks — see VERIFY.md]
```

### CONTEXT.md template

This file preserves the planner's domain knowledge for the executor. Fill it in during planning and keep it in Aider's read-only context during execution.

```markdown
# CONTEXT.md — [Repo/Feature Name]

## Relevant files

- `src/path/to/key_file.py` — [What it does, why it matters]
- `src/path/to/another.py` — [Relationship to this task]

## Known invariants

- [Rule the code must never violate — e.g., "user IDs are always UUIDs, never integers"]
- [Business rule — e.g., "free tier users cannot have more than 3 active items"]

## Public API contracts

- `function_name(args) -> ReturnType` — [What callers expect; do not change signature]
- [Endpoint / interface that external systems depend on]

## Data model assumptions

- [Schema constraint the executor must respect]
- [Enum values that must stay stable]

## Style examples

- See `src/models/example.py` for the canonical pattern for this type of change
- Naming convention: [e.g., "all event handlers are named handle_X"]

## Do-not-change areas

- `src/auth/` — any changes here require human review, not AI execution
- `src/billing/` — same
- [Specific functions or classes that are off-limits for this task]

## Open questions

- [Anything unresolved that the executor should flag rather than guess at]

## Rollback plan

- [How to undo this change if something goes wrong post-merge]
```

### VERIFY.md template

One of these per repo. Defines what "done" means before commit and before merge. Customize for your stack.

```markdown
# VERIFY.md — [Repo Name]

## Required before commit

- [ ] Unit tests pass: `pytest -x --no-header`
- [ ] Type check passes: `mypy src/` (or `tsc --noEmit`)
- [ ] Lint passes: `ruff check .` (or `eslint src/`)
- [ ] Format check: `ruff format --check .` (or `prettier --check`)
- [ ] Affected integration tests pass: [command]

## Required before merge

- [ ] Full CI green (all of the above + slow tests)
- [ ] Security scan: [tool and command]
- [ ] Migration dry run (if schema changed): [command]
- [ ] Human review of diff
- [ ] Human review required (do not merge AI output alone) for:
  - Authentication or authorization changes
  - Payment or billing changes
  - Database migrations
  - Public API changes
  - Security-sensitive logic

## Stack-specific checks

[Add your repo's specific checks here — e.g., Storybook build, E2E tests, snapshot updates]

## Notes

- If a check fails and you're not sure why: do not escalate to cloud with the error in context
  if the failing output might contain sensitive data. Sanitize first.
```

---

## Appendix F: CURRENT_LIMITS — Provider Facts

> **This appendix is intentionally disposable.** Provider pricing, model names, rate limits, and plan structures change frequently. The information here was accurate as of writing but should be verified against the links below before making any decisions based on it.
>
> **Last verified:** April 2026
> **Confidence:** Moderate — spot-checked against provider docs at time of writing

### Claude (Anthropic)

- **Docs:** https://docs.anthropic.com / https://www.anthropic.com/pricing
- **Claude Code Pro:** Shared usage with Claude.ai Pro subscription. Rate limits vary — roughly 40-80 messages per 5-hour window for heavy agentic work, but Anthropic does not publish exact numbers and adjusts them. Extra usage beyond plan limits can be covered by API credits.
- **Current frontier model:** claude-opus-4-6 (check docs for latest)
- **Plan tiers:** Pro ($20/mo), Max 5× (~$100/mo), Max 20× (~$200/mo)

### OpenAI (ChatGPT / Codex)

- **Docs:** https://platform.openai.com/docs / https://openai.com/pricing
- **ChatGPT Plus:** $20/month. ChatGPT Pro: separate higher tier.
- **Codex:** Pricing has shifted to token-based — verify current model and pricing at platform.openai.com before assuming per-message cost.
- **Current frontier model:** Check openai.com for latest GPT model names

### Groq

- **Docs:** https://console.groq.com / https://groq.com/pricing
- **Free tier limits:** Apply at the organization level, not per user. Subject to change. Verified figures at the time of writing:

| Model | RPM | RPD | TPM | Notes |
|---|---|---|---|---|
| llama-3.1-8b-instant | 30 | 14,400 | 6,000 | Fast trivial tasks |
| llama-3.3-70b-versatile | 30 | 1,000 | 12,000 | Default fallback |
| qwen/qwen3-32b | 60 | 1,000 | 6,000 | Higher RPM |
| openai/gpt-oss-120b | 30 | 1,000 | 8,000 | Best free quality |
| llama-4-scout-17b-16e | 30 | 1,000 | 30,000 | Long context |

- **Data retention:** Groq does not retain customer data by default but may temporarily log inputs/outputs for reliability. Zero Data Retention controls are available — check your org settings before routing INTERNAL work through Groq.

---

## Appendix G: Metrics & Local Model Eval

### Lightweight Routing Log

You don't need a full observability stack. Start with a CSV log and review it weekly. The goal is to see where your actual failure patterns are, not to hit the 70/15/10/5 split on a particular day.

**`logs/ai-routing.csv` schema:**

```
date, repo, task_type, tier_used, model, escalated_from,
tests_passed, diff_lines_approx, human_rework_minutes, outcome
```

**Meaningful things to track:**

- Which tier do you actually escalate to most often? (If it's not Tier 1, your plans may be too vague)
- Where does human rework happen most? (Auth? Migrations? Specific repos?)
- Which failure modes repeat? (Update this doc when patterns emerge)
- What fraction of tasks are you handling manually because orchestration isn't worth it?

Review once a week for the first month. The architecture should be optimized from observed failure patterns, not expected model quality.

### Local Model Acceptance Benchmark

Before promoting a new local model to Tier 1, run it against these task types in a real repo. Grade pass/fail and note how many human edits were required.

**Benchmark tasks:**

| Task | What to test |
|---|---|
| Add a validation rule | Does it modify only the right file? Does it follow existing patterns? |
| Update an API endpoint | Does it preserve the public contract? Does it update tests? |
| Add a unit test | Is the test actually meaningful, or just green-washing? |
| Fix a known bug | Does it fix the root cause or paper over it? |
| Small refactor | Does it stay in scope? Does it break unrelated tests? |
| Update docs from code | Does it accurately reflect the implementation? |

**Scoring:**

| Metric | Record |
|---|---|
| Tests pass after change (no human edit) | pass / fail |
| Human edits required | count |
| Files touched that weren't in the spec | count |
| Latency for the task | minutes |

**Promotion rule:** A model is Tier 1-ready for a given repo when it passes at least 4/6 tasks with zero unspecified file edits. Run this eval again when you upgrade quantization or switch model families.

---

*Document version: 2.0*
*Last updated: April 2026*
*Architecture validated on: PowerSpec G762 (RTX 5080 16GB)*
*Changelog: v2.0 — Added CONTEXT.md as third phase artifact; added VERIFY.md per-repo verification contract; added two-mode auto-commit config; added objective escalation triggers; added data classification and egress controls (Appendix D); added artifact templates (Appendix E); moved provider facts to dated appendix (Appendix F); added metrics schema and local model eval (Appendix G); mandatory Git worktrees for parallel work; judge scoring dimensions for parallel exploration; three-gate final approval for review phase; "manual is faster" escape hatch in routing logic; VRAM tier table in hardware section.*
