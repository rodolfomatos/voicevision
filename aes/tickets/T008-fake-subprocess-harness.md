---
ticket: T008
title: Fake-subprocess test harness
sprint: sprint-02
priority: high
status: done
created: 2026-10-09
---

# T008 — Fake-subprocess test harness

## Context

T009–T011 are untestable without a way to run a child process deterministically.
Without this, the team either installs real models to run unit tests (slow,
fragile, CI-hostile) or skips testing process handling entirely — which is
precisely the code most likely to break.

## Acceptance Criteria

- [ ] A fixture that spawns a real `python -c` child via `SubprocessBackend`
- [ ] Behaviours a fake child can be asked to exhibit:
  - echo stdin to stdout
  - emit N bytes of stderr, then stdout (drives the deadlock test)
  - exit 0 / exit non-zero / exit on signal
  - sleep longer than the caller's timeout
  - emit non-UTF-8 bytes on stdout
  - die mid-write
- [ ] Behaviour is selected by argv so one fixture covers all backends
- [ ] A spawn-counting fixture for asserting warm reuse (FR-7)
- [ ] No real model binaries required; no network
- [ ] Harness lives in `tests/`, not shipped in `src/`

## Scope

**In scope:** `tests/support/fake_child.py` + fixtures.

**Out of scope:** changes to `SubprocessBackend` (that is T007).

## Dependencies

T007.

## Rollback

Delete the harness. T007's own tests would need inlining.

## Known Risks

- The harness itself could mask bugs if it diverges from real process
  behaviour. Mitigation: it uses real `Popen`, not mocks.
- Timing-sensitive tests (timeout, deadlock) can flake on loaded CI.
  Prefer generous margins and explicit synchronisation over short sleeps.

## Notes

This ticket is a dependency for three tickets and is small. Do not defer it
behind the backends it exists to test.