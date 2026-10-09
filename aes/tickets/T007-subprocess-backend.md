---
ticket: T007
title: SubprocessBackend base class
sprint: sprint-02
priority: high
status: done
created: 2026-10-09
---

# T007 — SubprocessBackend base class

## Context

The riskiest ticket in the project. Every real backend (T009, T011) inherits
this; the LLM backend (T010) diverges to HTTP and reuses only the supervision
part. ADR-002 is unimplementable without it.

This class owns process lifecycle, and naive implementations of that are a
well-known source of deadlocks. Design it once.

## Acceptance Criteria

- [ ] `SubprocessBackend.__init__` takes argv (a **list**, never a string) and
      optional `cwd`, `env`, `timeout`
- [ ] Lazy spawn: no process is created in `__init__`. First call spawns.
- [ ] **Warm reuse (FR-7)**: the second call does not spawn a second process.
      Asserted by counting `Popen` invocations.
- [ ] `communicate(payload, timeout)` writes payload to stdin, closes stdin,
      reads stdout, returns bytes. stderr is captured concurrently and never
      left to fill its pipe.
- [ ] **No deadlock (the acceptance test that matters):** a child that writes
      > 64 KB to stderr while the parent waits on stdout must not hang. Write
      the fake child so it does exactly that.
- [ ] Dead-process detection: if `proc.poll()` is not `None` before a call,
      the process is respawned transparently.
- [ ] **Single restart (FR-9)**: if the child dies *during* a call, retry once,
      then raise `BackendExecutionError` carrying the last stderr.
- [ ] `BackendExecutionError` message includes the command, exit code, and
      tail of stderr. A bare "failed" is a bug (FR-10).
- [ ] `close()` terminates, then escalates to `kill()` after a grace period,
      and is idempotent.
- [ ] Non-zero exit surfaces as an error, never as empty output.
- [ ] Class-level `available()` probe returns `bool`, overridable.
- [ ] `install_hint` attribute naming the package that provides the binary.
- [ ] mypy `--strict` clean; no `shell=True` anywhere (bandit gate).

## Scope

**In scope:** `src/voicevision/backends/subprocess_backend.py` + tests.

**Out of scope:** the concrete backends; HTTP transport for the LLM.

## Dependencies

None. This is the foundation for Sprint 3.

## Rollback

Delete the file. Nothing depends on it yet.

## Known Risks

- **Deadlock is the default failure mode.** Most implementations get this wrong
  first. Budget time for it; do not treat the happy-path test as sufficient.
- **Zombie processes** if `close()` is never called. Document the context
  manager; add `__del__` as a backstop, not as the primary mechanism.
- **`timeout` semantics**: on timeout, the child must be killed or it leaks.
- **Binary stdout**: whisper/piper may emit non-UTF-8. Decoding is the caller's
  decision, not this class's — return bytes.

## Notes

Test without real models. Use `sys.executable -c '...'` as a fake child so the
tests exercise the real `Popen` code path with zero external dependencies.