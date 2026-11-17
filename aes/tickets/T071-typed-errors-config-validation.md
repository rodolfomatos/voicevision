---
ticket: T071
title: Typed Errors + Config Validation
sprint: M1-core-abstraction
priority: high
status: todo
created: 2026-11-16
---

# T071 — Typed Errors + Config Validation

## Context

M1.3 from architecture audit. Error handling is inconsistent. Need comprehensive typed exception hierarchy and fail-fast config validation at VoicePipeline construction.

## Acceptance Criteria

- [ ] `voicevision.errors` defines exception hierarchy:
  - `VoiceVisionError` (base)
    - `ConfigurationError` — invalid config, missing required fields
    - `ProviderError` — provider-level failures
      - `ProviderUnavailable` — backend not installed/configured
      - `ProviderTimeout` — deadline exceeded
      - `ProviderConfigError` — invalid provider config
      - `ProviderRuntimeError` — subprocess crash, stdout/stderr capture
    - `PipelineError` — pipeline orchestration failures
      - `PipelineCancelled` — cancellation token triggered
      - `PipelineInterrupted` — barge-in interruption
      - `PipelineStateError` — invalid state transition
    - `AudioError` — capture, playback, format issues
    - `ModelError` — model download, loading, compatibility
- [ ] All exceptions carry: `provider` (str), `modality` (str), `context` (dict), `cause` (Exception)
- [ ] `voicevision.core.config.PipelineConfig`:
  - Fail-fast validation in `__init__` / `model_post_init`
  - Validates: at least one provider per required modality registered
  - Validates: model paths exist (for local models)
  - Validates: numeric ranges (timeouts, sample rates, buffer sizes)
  - Validates: mutually exclusive options (streaming vs non-streaming)
  - Returns clear error messages with field paths
- [ ] Config validation runs at `VoicePipeline` construction, not first use
- [ ] Unit tests: all error types, config validation success/failure cases

## Scope

**In scope:**
- `src/voicevision/errors.py` — rewrite
- `src/voicevision/core/config.py` — add validation
- `tests/core/test_errors.py`, `tests/core/test_config_validation.py`

**Out of scope:**
- Provider implementations
- Registry

## Dependencies

- T069, T070 (protocols, registry)

## Rollback

Git revert.

## Known Risks

- **Validation timing**: Too early = breaks lazy imports. Must validate after registry populated.
- **Error proliferation**: Keep hierarchy shallow. Max 3 levels.
- **Backwards compatibility**: Existing try/except must still work.

## Notes

- Use `pydantic.ValidationError` for config, wrap in `ConfigurationError`
- Subprocess errors must capture stderr (FR-15 from REQUIREMENTS)
- `PipelineCancelled` must be distinct from `ProviderTimeout`