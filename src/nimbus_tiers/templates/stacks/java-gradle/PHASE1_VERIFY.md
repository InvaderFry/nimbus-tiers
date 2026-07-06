# Phase 1 verify.sh helper — Gradle (Spring-aware)

Inline this helper into `verify.sh` only when the project's sentinel is
`build.gradle` or `build.gradle.kts`. For non-Spring Gradle projects, drop
the `spring.*` system properties.

```bash
run_tests_quiet() {
  local verify_log="build/verify.log"
  mkdir -p build

  ./gradlew --console=plain --warning-mode=summary test \
    -Dspring.main.banner-mode=off \
    -Dlogging.level.root=ERROR \
    -Dlogging.level.org.springframework=ERROR \
    >"$verify_log" 2>&1 &
  local gradle_pid=$!

  local heartbeat_interval=60
  local elapsed=0
  while kill -0 "$gradle_pid" 2>/dev/null; do
    sleep "$heartbeat_interval"
    elapsed=$((elapsed + heartbeat_interval))
    if kill -0 "$gradle_pid" 2>/dev/null; then
      echo "verify.sh: Gradle still running after ${elapsed}s..."
    fi
  done

  # Capture wait's REAL exit status. Do NOT write `if ! wait "$pid"; then
  # status=$?` — inside that branch `$?` is the status of the *negated* test
  # (always 0), so every Gradle failure is recorded as success and a broken
  # build gets committed as a passing step. `|| var=$?` is errexit-safe and
  # preserves the real code.
  local gradle_status=0
  wait "$gradle_pid" || gradle_status=$?

  if [ "$gradle_status" -eq 0 ]; then
    return 0
  fi

  if grep -E -q \
    'Could not self-attach|MockitoInitializationException|Byte Buddy mock maker|MockMaker|Can not attach to current VM' \
    "$verify_log"; then
    echo "verify.sh: INFRA failure: Mockito/Byte Buddy agent attach failed."
    echo "verify.sh: likely fix: add test resource mockito-extensions/org.mockito.plugins.MockMaker=mock-maker-subclass, or fix JVM attach support."
    echo "verify.sh: full log: $verify_log"
    return 1
  fi

  awk '
    /^> Task .*FAILED/ {print}
    /APPLICATION FAILED TO START/ {show=1; count=0}
    show && count < 35 {print; count++}
    /Caused by:/ {print}
    / FAILED$/ {print}
    /BUILD FAILED/ {print}
  ' "$verify_log"

  echo "verify.sh: full log: $verify_log"
  return 1
}
```

Notes:

- `--console=plain` and `--warning-mode=summary` strip ANSI noise and
  deprecation chatter without hiding failures.
- Full Gradle output is written to `build/verify.log`; only filtered failures
  are printed to stdout.
- `verify.sh` already runs under `set -euo pipefail`. Keep `set -o pipefail`
  in scope so a Gradle failure isn't masked by log filtering.
- Never wrap `wait` (or any status-bearing command) in `if !` and read `$?`
  inside the branch — that reads the *negated* test's status (always 0) and
  silently converts build failures into passes. Capture the status
  immediately: `cmd || rc=$?`, or `rc=$?` on the very next line.
- The filter preserves task-level failures, application-startup failures,
  "Caused by" chains, individual test failures, and `BUILD FAILED`.
- The heartbeat emits one short line every 60 seconds while Gradle is still
  running to make long test runs visible without spamming context.
- If tests fail with a Mockito/Byte Buddy self-attach error in restricted
  environments (common in WSL/containers), the scaffolded project already
  includes `src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker`
  with `mock-maker-subclass`. If the error still appears, verify the file was
  copied correctly and that inline mocking is not explicitly required.
- Do not paste this helper into a non-Gradle project's `verify.sh`.
