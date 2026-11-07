---
ticket: T022
title: v0.1 final cleanup — fix remaining ruff issues and complete polish
sprint: sprint-03
priority: medium
status: pending
created: 2026-11-07
---

# T022 — v0.1 final cleanup — fix remaining ruff issues and complete polish

## Context

After T021 (ruff debt cleanup), there are still some ruff findings in older files:
- tests/test_pipeline.py: E501 (line too long), C901 (complexity)
- Other minor issues across the codebase

The v0.1 voice loop is functionally complete. This ticket is the final polish to ensure the project is in a clean, production-ready state.

## Acceptance Criteria

- [ ] `ruff check src/voicevision tests` reports 0 errors
- [ ] `ruff format --check src/voicevision tests` reports no changes needed
- [ ] `mypy --strict src/voicevision` reports 0 errors (or only pre-existing)
- [ ] All 71+ tests pass
- [ ] `make check` reports 0 failures (except pre-existing environment-dependent tests)
- [ ] docs/VOICE_INPUT.md updated with complete vision example
- [ ] README.md updated with complete vision example

## Scope

**In scope:** Remaining ruff findings, documentation updates, final polish.

**Out of scope:** New functionality, new features, architectural changes.

## Dependencies

None — standalone cleanup task.

## Rollback

Revert individual files if any test regression is introduced.

## Known Risks

- Fixing line length issues may require rewriting lines, which could introduce typos. All tests must pass after cleanup.
- C901 complexity issues may require refactoring that changes code structure. Keep changes minimal.

## Notes

- Run `ruff check src/voicevision tests` to see the full list before starting.
- Run `ruff check --fix` for auto-fixable issues.
- Manual fixes needed for C901 (complexity), E501 (line length).
