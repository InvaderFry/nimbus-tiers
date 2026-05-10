# Phase 1 verify.sh helper — Maven (Spring-aware)

Inline this helper into `verify.sh` only when the project's sentinel is
`pom.xml`. For non-Spring Maven projects, drop the `spring.*` system
properties.

```bash
run_tests_quiet() {
  ./mvnw --batch-mode test \
    -Dspring.main.banner-mode=off \
    -Dlogging.level.root=ERROR \
    -Dlogging.level.org.springframework=ERROR \
    -Ddebug=false \
    -Dspring.test.context.failure.threshold=1 \
    -DtrimStackTrace=true \
    2>&1 | awk '
      /APPLICATION FAILED TO START/ {show=1; count=0}
      show && count < 35 {print; count++}
      /\[ERROR\]/ {print}
      /Caused by:/ {print}
      /No qualifying bean/ {print}
      /BUILD FAILURE/ {print}
    '
}
```

Notes:

- `verify.sh` already runs under `set -euo pipefail`. Keep `set -o pipefail`
  in scope so a Maven failure isn't masked by the `awk` filter.
- The filter preserves application-startup failures, errors, "Caused by"
  chains, missing-bean diagnostics, and `BUILD FAILURE` — everything else
  is dropped.
- Do not paste this helper into a non-Maven project's `verify.sh`.
