---
ticket: T069
title: Provider Protocol Interfaces — STT, LLM, TTS, VAD, Vision, WakeWord, SpeakerID, Emotion
sprint: M1-core-abstraction
priority: high
status: todo
created: 2026-11-16
---

# T069 — Provider Protocol Interfaces

## Context

M1.1 from architecture audit. The current `core/protocols.py` defines 5 protocols but they are incomplete and don't cover all modalities (SpeakerID, Emotion, WakeWord). We need comprehensive, versioned protocol interfaces that enable true provider interchangeability.

## Acceptance Criteria

- [ ] `voicevision.core.protocols` defines 8 Protocol classes with proper type hints, docstrings, `__slots__ = ()`:
  - `STTProvider` — transcribe, stream, detect_language, available, install_hint
  - `LLMProvider` — generate, stream, available, install_hint
  - `TTSProvider` — synthesize, stream, available, install_hint
  - `VADProvider` — process_frame, is_speech, available, install_hint
  - `VisionProvider` — describe, analyze, available, install_hint
  - `WakeWordProvider` — process_frame, check, available, install_hint
  - `SpeakerIDProvider` — identify, enroll, available, install_hint
  - `EmotionProvider` — detect, available, install_hint
- [ ] All protocols inherit from `Provider` base with `capabilities()` -> `ProviderCapabilities` and `lifecycle()` -> `ProviderLifecycle`
- [ ] `ProviderCapabilities` dataclass: streaming, languages, models, max_concurrent
- [ ] `ProviderLifecycle` protocol: `initialize()`, `shutdown()`, `health_check()`
- [ ] Streaming methods return `AsyncGenerator` with proper chunk types
- [ ] Error types: `ProviderError`, `ProviderUnavailable`, `ProviderTimeout`, `ProviderConfigError`
- [ ] Unit tests for each protocol (mock implementations)

## Scope

**In scope:**
- `src/voicevision/core/protocols.py` — complete rewrite
- `src/voicevision/core/errors.py` — add provider error types
- `tests/core/test_protocols.py`

**Out of scope:**
- Concrete implementations (existing backends will be adapted in T070)
- Registry (T070)

## Dependencies

- T002 (existing protocols) — baseline
- Requires: `typing-extensions`, `pydantic` (for config models)

## Rollback

Git revert this ticket's changes.

## Known Risks

- **Breaking changes**: Existing backends must be adapted. Plan migration in T070.
- **Protocol granularity**: Too fine-grained = explosion of types. Balance with practical use.
- **Async vs Sync**: Some backends are sync (subprocess), some async (HTTP). Protocols must accommodate both.

## Notes

- Use `typing.Protocol` for structural subtyping
- Streaming: define `STTChunk`, `LLMChunk`, `TTSChunk` typed dicts/dataclasses
- `available()` must be fast (no network/model loading)
- `install_hint` returns user-actionable string