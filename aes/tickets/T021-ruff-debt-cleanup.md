---
ticket: T021
title: Ruff debt cleanup — fix 36 pre-existing lint errors
sprint: sprint-03
priority: medium
status: pending
created: 2026-11-07
---

# T021 — Ruff debt cleanup — fix 36 pre-existing lint errors

## Context

The voicevision repo has 36 pre-existing ruff findings in files that were not
created by the current voice loop work (piper.py, vad.py, pipeline.py,
test_piper.py, test_vad.py, test_pipeline.py). These include unused imports,
missing newlines, deprecated typing, overly complex functions, and import order
issues. They do not affect functionality but block `make check` from being fully
green.

## Acceptance Criteria

- [ ] `ruff check src/voicevision tests` reports 0 errors
- [ ] `ruff format --check src/voicevision tests` reports no changes needed
- [ ] All 71 existing tests still pass
- [ ] No functional changes to any file (surgical lint fixes only)

## Scope

**In scope:** `src/voicevision/backends/piper.py`, `src/voicevision/backends/vad.py`,
`src/voicevision/pipeline.py`, `tests/test_piper.py`, `tests/test_vad.py`,
`tests/test_pipeline.py` (any file with ruff findings).

**Out of scope:** New functionality, refactoring logic, changing behavior.

## Dependencies

None — standalone cleanup task.

## Rollback

Revert individual files if any test regression is introduced.

## Known Risks

- Fixing lint issues could theoretically introduce subtle bugs if imports or
  logic are changed incorrectly. All tests must pass after cleanup.
- Some findings (e.g., C901 complexity) may require refactoring that changes
  code structure. Keep changes minimal.

## Notes

- Run `ruff check src/voicevision tests` to see the full list before starting.
- Run `ruff check --fix` for auto-fixable issues (import sorting, unused
  imports, trailing newlines).
- Manual fixes needed for C901 (complexity), E501 (line length), etc.
