# Phase 1 verify.sh helper — Rust (cargo test)

Inline this helper into `verify.sh` only when the project uses the standard
`cargo` toolchain.

```bash
require_cargo() {
  # An initialized project (Cargo.toml present) with no Rust toolchain is an
  # INFRASTRUCTURE failure and must exit non-zero. Exiting 0 here lets
  # phase2.sh record a step DONE without ever compiling a line — the gate
  # stops being authoritative. Only a missing *sentinel* (Cargo.toml) may
  # exit 0.
  if ! command -v cargo >/dev/null 2>&1; then
    echo "ERROR: cargo toolchain not found — cannot run the test gate." >&2
    echo "Install Rust (https://rustup.rs), then re-run verify.sh." >&2
    exit 1
  fi
}

run_tests_quiet() {
  cargo test --quiet 2>&1 | awk '
    /^error/ {show=1}
    /^warning: unused/ {next}
    /---- .* stdout ----/ {show=1}
    /^test .* FAILED/ {print; next}
    /^failures:/ {show=1}
    /^test result:/ {print; show=0; next}
    show {print}
  '
}
```

Notes:

- Call `require_cargo` immediately after the sentinel check (`Cargo.toml`
  missing → exit 0 is allowed; anything else is not) and before
  `run_tests_quiet`.
- `cargo test` compiles before testing, so a build break fails the gate with
  the compiler error shown — no separate build step needed. `--quiet`
  suppresses the per-test dot spam but keeps failures and the final
  `test result:` summary.
- Keep `set -o pipefail` in scope so a failing test run propagates through
  the `awk` filter.
- Do NOT write `if ! wait "$pid"; then status=$?` anywhere in verify.sh —
  inside that branch `$?` is the status of the negated test (always 0) and
  every failure would report success. If you background the test run,
  capture the status directly: `wait "$cargo_pid" || cargo_status=$?`.
- For static checks (`cargo clippy`, `cargo fmt --check`), call them outside
  `run_tests_quiet` and let their own non-zero exits surface.
