# Phase 1 verify.sh helper — Node (npm test)

Inline this helper into `verify.sh` only when the project's sentinel is
`package.json`. The default snippet assumes Jest-style output; adjust the
filter patterns for vitest, mocha, or another runner.

```bash
run_tests_quiet() {
  npm test --silent 2>&1 | awk '
    /^FAIL/ {print}
    /^PASS/ {next}
    /✕|✗/ {print}
    /^Tests:/ {print}
    /^Test Suites:/ {print}
    /^Snapshots:/ {next}
    /^Time:/ {next}
    /Error:/ {print}
    /at .*\.(js|ts|tsx|mjs|cjs):[0-9]+/ {print}
  '
}
```

Notes:

- `--silent` suppresses npm's lifecycle banners; the test runner's own
  output is preserved.
- Keep `set -o pipefail` in scope so a failing test run propagates through
  the `awk` filter.
- The filter preserves failed-suite headers, individual failed assertions,
  the summary block, and stack frames pointing at JS/TS source — passing
  suites and timing/snapshot lines are dropped.
- For projects that use vitest, swap the runner invocation
  (`npx vitest run --reporter=basic`) and verify the patterns above still
  match the chosen reporter's failure lines.
- Do not paste this helper into a non-Node project's `verify.sh`.
