# Phase 1 verify.sh helper — Go (go test)

Inline this helper into `verify.sh` only when the project uses the standard
`go test` toolchain.

```bash
require_go() {
  # An initialized project (go.mod present) with no Go toolchain is an
  # INFRASTRUCTURE failure and must exit non-zero. Exiting 0 here lets
  # phase2.sh record a step DONE without ever compiling a line — the gate
  # stops being authoritative. Only a missing *sentinel* (go.mod) may exit 0.
  if ! command -v go >/dev/null 2>&1; then
    echo "ERROR: go toolchain not found — cannot run the test gate." >&2
    echo "Install Go (https://go.dev/dl/), then re-run verify.sh." >&2
    exit 1
  fi
}

run_tests_quiet() {
  go test ./... 2>&1 | awk '
    /^--- FAIL/ {print; next}
    /^FAIL/ {print; next}
    /^ok / {print; next}
    /panic:/ {show=1}
    /cannot find|undefined:|syntax error|build failed/ {print; next}
    show {print}
  '
}
```

Notes:

- Call `require_go` immediately after the sentinel check (`go.mod` missing →
  exit 0 is allowed; anything else is not) and before `run_tests_quiet`.
- `go test ./...` compiles everything it tests, so a build break fails the
  gate with the compiler error shown — no separate build step needed.
- Keep `set -o pipefail` in scope so a failing test run propagates through
  the `awk` filter.
- Do NOT write `if ! wait "$pid"; then status=$?` anywhere in verify.sh —
  inside that branch `$?` is the status of the negated test (always 0) and
  every failure would report success. If you background the test run,
  capture the status directly: `wait "$go_pid" || go_status=$?`.
- For static checks (`go vet`, `staticcheck`), call them outside
  `run_tests_quiet` and let their own non-zero exits surface.
