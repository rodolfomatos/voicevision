---
ticket: T003
title: Dummy backends for all 5 modalities
sprint: sprint-01
priority: high
status: pending
created: 2025-10-08
---

# T003 — Dummy backends for all 5 modalities

## Context

Provide zero-dependency, fast, deterministic implementations of all 5 protocols for unit testing and CI. These are the "test doubles" that enable testing business logic without model downloads or hardware.

## Acceptance Criteria

- [ ] `voicevision.backends.dummy` module with 5 classes:
  - `DummyLLM` — returns `config.response_template` (default: "Dummy response")
  - `DummySTT` — returns `config.transcript` (default: "dummy transcript")
  - `DummyTTS` — returns valid WAV bytes (440Hz tone, 1s, 16-bit mono)
  - `DummyVision` — returns `config.description` (default: "dummy image description")
  - `DummyCamera` — returns synthetic PNG bytes (gradient or checkerboard)
- [ ] Each dummy accepts config via constructor for customization
- [ ] All dummies registered in `BackendRegistry` under names "dummy"
- [ ] Import time < 10ms (no heavy imports)
- [ ] Unit tests verify each dummy implements its protocol correctly

## Scope

**In scope:**
- `src/voicevision/backends/dummy.py`
- Registration in `src/voicevision/__init__.py` or auto-discovery
- Tests in `tests/backends/test_dummy.py`

**Out of scope:**
- Any real backend implementations
- Audio/video encoding libraries (generate WAV/PNG manually with stdlib)

## Dependencies

- T002 (protocols + registry) — must be complete

## Rollback

Delete `src/voicevision/backends/dummy.py` and remove registration.

## Known Risks

- **WAV/PNG generation**: Must produce valid files without external deps. Use `wave` and `struct` modules for WAV; minimal PNG via `struct` + `zlib`.
- **Protocol compliance**: Dummies must match protocol signatures exactly. Use `typing.Protocol` structural checking.

## Notes

- WAV: 440Hz sine wave, 16-bit, 16kHz mono, 1 second → ~32KB
- PNG: 64x64 gradient, no IDAT compression needed for test validity
- Consider `@dataclass` for dummy configs