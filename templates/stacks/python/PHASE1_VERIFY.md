# Phase 1 verify.sh helper — Python (pytest)

Inline this helper into `verify.sh` only when the project uses pytest.
Adapt the runner invocation if the project standardizes on `unittest`,
`nox`, or `tox` instead.

```bash
require_venv() {
  # An initialized project (sentinel present) with no virtualenv is an
  # INFRASTRUCTURE failure and must exit non-zero. Exiting 0 here lets
  # phase2.sh record a step DONE without ever running a single test —
  # the gate stops being authoritative. Only a missing *sentinel*
  # (pyproject.toml / requirements.txt) may exit 0.
  if [ ! -f ".venv/bin/activate" ]; then
    echo "ERROR: .venv not found — cannot run the test gate." >&2
    echo "Create it, then re-run verify.sh:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
}

run_tests_quiet() {
  python -m pytest -q --tb=short --no-header 2>&1 | awk '
    /^=+ ERRORS =+/ {show=1}
    /^=+ FAILURES =+/ {show=1}
    show {print; next}
    /^FAILED/ {print}
    /^ERROR/ {print}
    /^=+ short test summary/ {print}
    /^=+ .* (failed|errors)/ {print}
    /^=+ .* passed/ {print}
  '
}
```

Notes:

- Call `require_venv` immediately after the sentinel check and before
  `run_tests_quiet`. Do not soften it into a warning, and do not silently
  fall back to a system Python: a "pass" produced without the project's
  pinned dependencies is not a pass.
- A missing `.venv` must exit **non-zero**. The PHASE1_SPEC "uninitialized →
  exit 0" allowance applies only to a missing sentinel file, never to a
  missing toolchain/environment on an initialized project.
- `-q --tb=short --no-header` keeps pytest output focused on failures while
  preserving short tracebacks.
- Keep `set -o pipefail` in scope so a failing test run propagates through
  the `awk` filter.
- For static checks (ruff, mypy), call them outside `run_tests_quiet` and
  let their own non-zero exits surface — they are already concise.
