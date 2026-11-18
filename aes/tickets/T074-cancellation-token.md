---
ticket: T074
title: Unified CancellationToken
sprint: M1-core-abstraction
priority: high
status: todo
created: 2026-11-18
---

# T074 — Unified CancellationToken

## Context

M1.6 from architecture audit. No cancellation mechanism exists. Need a unified `CancellationToken` that propagates through all providers, pipeline stages, and enables barge-in, timeout handling, and graceful shutdown.

## Acceptance Criteria

- [ ] `voicevision.core.cancellation.CancellationToken` class:
  - `cancelled: bool` property (read-only)
  - `cancel() -> None` — triggers cancellation
  - `throw_if_cancelled() -> None` — raises `PipelineCancelled` if cancelled
  - `on_cancel(callback: Callable[[], None]) -> None` — registers callback
  - `link(other: CancellationToken) -> None` — cancels when other cancels
  - `child() -> CancellationToken` — creates child token (cancels when parent cancels)
  - `with_timeout(seconds: float) -> CancellationToken` — auto-cancels after timeout
  - `__enter__` / `__exit__` — context manager auto-cancels on exit
- [ ] `CancellationToken.none()` — singleton never-cancelled token
- [ ] Integration with `asyncio`:
  - `async wait() -> None` — awaits cancellation
  - `async shield(coro, token) -> Any` — runs coro, cancels on token
- [ ] Integration with `subprocess`:
  - `SubprocessBackend` accepts `token: CancellationToken`
  - On cancel: sends SIGTERM, waits, then SIGKILL
  - Captures stderr on forced termination
- [ ] Integration with providers (T069):
  - All provider methods accept optional `token: CancellationToken`
  - Streaming generators check token each yield
  - Long operations (model inference) check periodically
- [ ] Integration with `VoicePipeline`:
  - `process()` and `process_stream()` accept `token`
  - Barge-in calls `session.cancellation_token.cancel()`
  - Timeout creates child token with deadline
- [ ] Unit tests: basic cancel, child tokens, timeout, linking, context manager, subprocess kill, provider integration

## Scope

**In scope:**
- `src/voicevision/core/cancellation.py` — new module
- `src/voicevision/backends/subprocess_backend.py` — update SubprocessBackend
- `tests/core/test_cancellation.py`

**Out of scope:**
- Barge-in detection logic (T087)
- Network request cancellation (future HTTP client)

## Dependencies

- T071 (errors) — `PipelineCancelled` exception
- T073 (sessions) — session owns cancellation token
- T069 (protocols) — provider method signatures

## Rollback

Git revert.

## Known Risks

- **Cancellation vs timeout**: Different semantics. Token = external request, timeout = deadline.
- **Subprocess cleanup**: Must not leave zombies. Use `tini`-style reaping.
- **Async cancellation**: `asyncio.CancelledError` vs custom exception. Use custom for clarity.
- **Performance**: Token check on hot path (per frame) must be fast (atomic bool).

## Notes

- Implement cancelled flag as `threading.Event` for sync, `asyncio.Event` for async
- `SubprocessBackend` already has deadline handling — extend with token
- Providers should check `token.throw_if_cancelled()` at yield points
- `PipelineCancelled` must bubble up and stop pipeline cleanly