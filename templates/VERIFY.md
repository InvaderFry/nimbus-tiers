# VERIFY.md — {{PROJECT_NAME}}

> Defines what "done" means for this repo, before commit and before merge. Customize the commands for your stack.

## Required before commit

- [ ] Unit tests pass: `pytest -x --no-header` _(or your runner)_
- [ ] Type check passes: `mypy src/` _(or `tsc --noEmit`, `pyright`, etc.)_
- [ ] Lint passes: `ruff check .` _(or `eslint src/`, `golangci-lint run`, etc.)_
- [ ] Format check: `ruff format --check .` _(or `prettier --check .`)_
- [ ] Affected integration tests pass: _[command]_

## Required before merge

- [ ] Full CI green (all of the above + slow tests)
- [ ] Security scan: _[tool and command — e.g., `trufflehog filesystem .`]_
- [ ] Migration dry run (if schema changed): _[command]_
- [ ] Human review of the diff
- [ ] Human review **required** (do not merge AI output alone) for:
  - Authentication or authorization changes
  - Payment or billing changes
  - Database migrations
  - Public API changes
  - Security-sensitive logic

## Stack-specific checks

- _Add your repo's specific checks here — e.g., Storybook build, E2E tests, snapshot updates, contract tests._

## Notes

- If a check fails and you're not sure why: do **not** escalate to cloud with the failing output in context if it might contain sensitive data (stack traces with connection strings, secrets, customer rows). Sanitize first.
