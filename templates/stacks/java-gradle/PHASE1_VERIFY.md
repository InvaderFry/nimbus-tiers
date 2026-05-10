# Phase 1 verify.sh helper — Gradle (Spring-aware)

Inline this helper into `verify.sh` only when the project's sentinel is
`build.gradle` or `build.gradle.kts`. For non-Spring Gradle projects, drop
the `spring.*` system properties.

```bash
run_tests_quiet() {
  ./gradlew --console=plain --warning-mode=summary test \
    -Dspring.main.banner-mode=off \
    -Dlogging.level.root=ERROR \
    -Dlogging.level.org.springframework=ERROR \
    2>&1 | awk '
      /^> Task .*FAILED/ {print}
      /APPLICATION FAILED TO START/ {show=1; count=0}
      show && count < 35 {print; count++}
      /Caused by:/ {print}
      / FAILED$/ {print}
      /BUILD FAILED/ {print}
    '
}
```

Notes:

- `--console=plain` and `--warning-mode=summary` strip ANSI noise and
  deprecation chatter without hiding failures.
- `verify.sh` already runs under `set -euo pipefail`. Keep `set -o pipefail`
  in scope so a Gradle failure isn't masked by the `awk` filter.
- The filter preserves task-level failures, application-startup failures,
  "Caused by" chains, individual test failures, and `BUILD FAILED`.
- Do not paste this helper into a non-Gradle project's `verify.sh`.
