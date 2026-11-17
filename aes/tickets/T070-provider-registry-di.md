---
ticket: T070
title: ProviderRegistry with Dependency Injection
sprint: M1-core-abstraction
priority: high
status: todo
created: 2026-11-16
---

# T070 — ProviderRegistry with Dependency Injection

## Context

M1.2 from architecture audit. Current `VoicePipeline` hardcodes backend instantiation. Need a registry that manages provider lifecycle, enables DI, and allows selecting providers by config without changing core code.

## Acceptance Criteria

- [ ] `voicevision.core.registry.ProviderRegistry` class:
  - `register(provider: Provider) -> None` — instance registration
  - `register_class(modality: str, name: str, cls: type[Provider], **kwargs) -> None` — lazy class registration
  - `get(modality: str, name: str) -> Provider` — returns initialized instance
  - `get_default(modality: str) -> Provider` — returns default for modality
  - `list(modality: str) -> list[str]` — available names
  - `list_all() -> dict[str, list[str]]` — all modalities
  - `set_default(modality: str, name: str) -> None`
  - `shutdown() -> None` — calls lifecycle.shutdown on all
- [ ] Registry is a singleton (module-level) but supports instance for testing
- [ ] `ProviderRegistry.create_from_config(config: PipelineConfig) -> ProviderRegistry` factory
- [ ] Integration with `PipelineConfig`: modality fields reference registered names
- [ ] Backwards compatibility: existing `BackendRegistry` wrapper maintained
- [ ] Unit tests: registration, retrieval, default selection, shutdown, config factory

## Scope

**In scope:**
- `src/voicevision/core/registry.py` — rewrite
- `src/voicevision/core/config.py` — update PipelineConfig to use registry names
- `tests/core/test_registry.py`

**Out of scope:**
- Concrete provider implementations (adapted in T069/T070 integration)

## Dependencies

- T069 (protocols) — must define Provider base and modalities

## Rollback

Git revert.

## Known Risks

- **Config migration**: PipelineConfig currently has backend class fields. Must migrate to string references.
- **Lazy vs eager init**: Some providers need warm-up (llama-server). Registry must support both.
- **Testing isolation**: Singleton registry leaks state between tests. Provide `ProviderRegistry.for_testing()`.

## Notes

- Modalities: "stt", "llm", "tts", "vad", "vision", "wakeword", "speakerid", "emotion"
- Default providers: "dummy" for all (from existing dummy backends)
- Config example: `stt_provider: "whisper-cpp"` not `stt_backend: WhisperCppBackend`