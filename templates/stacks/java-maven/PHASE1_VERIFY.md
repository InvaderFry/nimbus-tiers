# Phase 1 verify.sh helper — Maven (Spring-aware)

Inline this helper into `verify.sh` only when the project's sentinel is
`pom.xml`. For non-Spring Maven projects, drop the `spring.*` system
properties.

```bash
run_tests_quiet() {
  local verify_log="target/verify.log"
  mkdir -p target

  ./mvnw --batch-mode test \
    -Dspring.main.banner-mode=off \
    -Dlogging.level.root=ERROR \
    -Dlogging.level.org.springframework=ERROR \
    -Ddebug=false \
    -Dspring.test.context.failure.threshold=1 \
    -DtrimStackTrace=true \
    >"$verify_log" 2>&1 &
  local mvn_pid=$!

  local heartbeat_interval=60
  local elapsed=0
  while kill -0 "$mvn_pid" 2>/dev/null; do
    sleep "$heartbeat_interval"
    elapsed=$((elapsed + heartbeat_interval))
    if kill -0 "$mvn_pid" 2>/dev/null; then
      echo "verify.sh: Maven still running after ${elapsed}s..."
    fi
  done

  local mvn_status=0
  wait "$mvn_pid" || mvn_status=$?

  if [ "$mvn_status" -eq 0 ]; then
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
    /APPLICATION FAILED TO START/ {show=1; count=0}
    show && count < 35 {print; count++}
    /\[ERROR\]/ {print}
    /Caused by:/ {print}
    /No qualifying bean/ {print}
    /BUILD FAILURE/ {print}
  ' "$verify_log"

  echo "verify.sh: full log: $verify_log"
  return 1
}
```

Notes:

- `verify.sh` already runs under `set -euo pipefail`. Keep `set -o pipefail`
  in scope so a Maven failure isn't masked by log filtering.
- Full Maven output is written to `target/verify.log`; only filtered failures
  are printed to stdout.
- The filter preserves application-startup failures, errors, "Caused by"
  chains, missing-bean diagnostics, and `BUILD FAILURE` — everything else
  is dropped.
- The heartbeat emits one short line every 60 seconds while Maven is still
  running to make long test runs visible without spamming context.
- If tests fail with a Mockito/Byte Buddy self-attach error in restricted
  environments (common in WSL/containers), add
  `src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker`
  with content `mock-maker-subclass` unless inline mocking is explicitly
  required.
- Do not paste this helper into a non-Maven project's `verify.sh`.
