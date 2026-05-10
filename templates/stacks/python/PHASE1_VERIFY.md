# Phase 1 verify.sh helper — Python (pytest)

Inline this helper into `verify.sh` only when the project uses pytest.
Adapt the runner invocation if the project standardizes on `unittest`,
`nox`, or `tox` instead.

```bash
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

- `verify.sh` should activate the project's virtualenv (e.g. source
  `.venv/bin/activate`) before calling `run_tests_quiet`, or rely on a
  pre-activated environment. Do not silently fall back to a system Python.
- `-q --tb=short --no-header` keeps pytest output focused on failures while
  preserving short tracebacks.
- Keep `set -o pipefail` in scope so a failing test run propagates through
  the `awk` filter.
- For static checks (ruff, mypy), call them outside `run_tests_quiet` and
  let their own non-zero exits surface — they are already concise.
