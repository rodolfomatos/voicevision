---
ticket: T005
title: CI pipeline (ruff, mypy, pytest, coverage)
sprint: sprint-01
priority: high
status: pending
created: 2025-10-08
---

# T005 — CI pipeline (ruff, mypy, pytest, coverage)

## Context

Establish automated quality gates per AES protocol. CI must run on every push/PR and block merge on failures.

## Acceptance Criteria

- [ ] `.github/workflows/ci.yml` with jobs:
  - `lint`: ruff + mypy strict + bandit
  - `test`: pytest unit tests with coverage ≥ 80%
  - `build`: python -m build (wheel + sdist)
- [ ] Matrix: Python 3.10, 3.11, 3.12 on ubuntu-latest
- [ ] Cache: `~/.cache/pip`, `~/.cache/ruff`, `~/.mypy_cache`
- [ ] Artifact: coverage.xml uploaded to Codecov (or similar)
- [ ] Badge in README (after T021)
- [ ] Pre-commit hooks mirror CI (ruff, mypy, bandit)

## Scope

**In scope:**
- `.github/workflows/ci.yml`
- `.pre-commit-config.yaml`
- Update `Makefile` targets if needed

**Out of scope:**
- Integration tests (require models/hardware)
- Android/RPi cross-compilation (future)
- Release automation (T022)

## Dependencies

- T002, T003, T004 (code to test)

## Rollback

Delete workflow file, revert pre-commit config.

## Known Risks

- **mypy strict + pydantic**: May need `# type: ignore` for pydantic internals. Use `plugins = ["pydantic.mypy"]`.
- **Coverage threshold**: Start at 80%, raise after foundation complete.
- **CI time**: Keep under 10 min. Unit tests only in CI; integration tests manual.

## Notes

- Use `uv` for faster installs in CI: `pipx install uv && uv sync`
- `ruff` replaces `black`, `isort`, `flake8` — single tool
- `bandit` for security lint (shell injection, etc.)