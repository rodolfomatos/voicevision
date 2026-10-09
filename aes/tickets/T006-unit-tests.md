---
ticket: T006
title: Unit tests for core + dummy backends
sprint: sprint-01
priority: high
status: pending
created: 2025-10-08
---

# T006 — Unit tests for core + dummy backends

## Context

Verify the foundation works. Tests are the specification — they define expected behavior and catch regressions.

## Acceptance Criteria

- [ ] `tests/core/test_protocols.py`:
  - Protocol structural subtyping works (dummy classes pass `isinstance` checks)
  - Method signatures enforced
- [ ] `tests/core/test_registry.py`:
  - Register/get/list/create roundtrip
  - Duplicate registration raises
  - Unknown modality/name raises
  - Create passes kwargs to backend constructor
- [ ] `tests/core/test_config.py`:
  - Config loads from env vars (`VOICEVISION_LLM_BACKEND=ollama`)
  - Config validation: invalid backend name raises
  - Config defaults to dummy backends
  - Extra fields forbidden
- [ ] `tests/backends/test_dummy.py`:
  - Each dummy returns expected type/format
  - DummyLLM.generate() returns str
  - DummySTT.transcribe() returns str
  - DummyTTS.synthesize() returns bytes (valid WAV header)
  - DummyVision.describe() returns str
  - DummyCamera.capture() returns bytes (valid PNG header)
- [ ] `tests/facade/test_voicevision.py` (depends on T004):
  - Facade instantiates with config
  - Lazy backend creation works
  - Context manager cleanup called
- [ ] Coverage ≥ 85% for core/ and backends/dummy.py

## Scope

**In scope:**
- All test files above
- `tests/conftest.py` fixtures (dummy configs, registry reset)

**Out of scope:**
- Integration tests with real backends
- Platform detection tests (T004)

## Dependencies

- T002, T003, T004

## Rollback

Delete test files.

## Known Risks

- **Registry singleton pollution**: Tests must reset registry between tests. Use fixture.
- **Config env var leakage**: Tests must isolate env vars. Use `monkeypatch`.
- **WAV/PNG validation**: Test actual file headers, not just bytes length.

## Notes

- Use `pytest-asyncio` for async protocol methods (if any)
- Fixtures: `dummy_config`, `clean_registry`, `mock_platform`
- Mark slow tests with `@pytest.mark.slow` (none expected here)