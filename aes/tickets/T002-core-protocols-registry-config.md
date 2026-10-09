---
ticket: T002
title: Core protocols + registry + config
sprint: sprint-01
priority: high
status: done
created: 2025-10-08
---

# T002 — Core protocols + registry + config

## Context

Establish the foundational types and wiring for voicevision. All subsequent backend implementations depend on these protocols and the registry pattern. This is the architectural backbone — get it right once.

## Acceptance Criteria

- [ ] `voicevision.core.protocols` defines 5 Protocol classes: `LLMBackend`, `STTBackend`, `TTSBackend`, `VisionBackend`, `CameraBackend`
- [ ] Each protocol has proper type hints, docstrings, and `__slots__ = ()`
- [ ] `voicevision.core.registry.BackendRegistry` implements:
  - `register(modality: str, name: str, backend_class: type) -> None`
  - `get(modality: str, name: str) -> type`
  - `list(modality: str) -> list[str]`
  - `create(modality: str, name: str, **kwargs) -> ProtocolInstance`
- [ ] `voicevision.core.config.VoiceVisionConfig` (pydantic BaseSettings):
  - All fields from FR-18 in REQUIREMENTS.md
  - Env var prefix `VOICEVISION_`
  - Validation: at least one backend per modality configured (or dummy)
- [ ] Lazy import pattern: no heavy deps imported at module level in core/
- [ ] Unit tests for registry CRUD and config validation

## Scope

**In scope:**
- `src/voicevision/core/protocols.py`
- `src/voicevision/core/registry.py`
- `src/voicevision/core/config.py`
- `src/voicevision/core/__init__.py` (exports)
- Tests in `tests/core/`

**Out of scope:**
- Any concrete backend implementations (T003, T007+)
- VoiceVision facade (T004)
- Platform detection (T004)

## Dependencies

- T001 (scaffolding) — done
- Requires: pydantic, pydantic-settings (in pyproject.toml)

## Rollback

Delete `src/voicevision/core/` and revert `src/voicevision/__init__.py` exports.

## Known Risks

- **Protocol design lock-in**: Changing protocols after backends exist is breaking. Review carefully.
- **Registry singleton vs. instance**: Current design uses class-level registry. May need instance-level for testing isolation.
- **Config validation timing**: Fail-fast at VoiceVision construction vs. lazy at first use. PRD says fail-fast.

## Notes

- Follow `src/voicevision/core/` pattern: one file per concern, minimal imports
- Use `typing.Protocol` (not ABC) for structural subtyping — enables duck-typing backends
- Registry keys: modality = "llm", "stt", "tts", "vision", "camera"
- Config fields use `Optional[...]` with defaults pointing to dummy backends