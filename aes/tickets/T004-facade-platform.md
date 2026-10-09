---
ticket: T004
title: VoiceVision facade + platform detection
sprint: sprint-01
priority: high
status: pending
created: 2025-10-08
---

# T004 — VoiceVision facade + platform detection

## Context

Provide the main user-facing API (`VoiceVision` class) and platform detection for automatic backend selection. This is the "lego brick" interface developers interact with.

## Acceptance Criteria

- [ ] `voicevision.VoiceVision` class (facade):
  - `__init__(config: VoiceVisionConfig | None = None, **overrides)`
  - Properties: `llm`, `stt`, `tts`, `vision`, `camera` → backend instances
  - Lazy instantiation: backends created on first access
  - `close()` / context manager for cleanup
- [ ] `voicevision.platform` module:
  - `Platform` enum: UBUNTU, RASPBERRY_PI, ANDROID_TERMUX, ANDROID_CHAQUOPY, UNKNOWN
  - `detect() -> Platform` — checks `/proc/device-tree/model`, `ANDROID_ROOT`, `TERMUX_VERSION`, etc.
  - `default_backends(platform: Platform) -> dict[str, str]` — returns backend names per modality
  - `check_dependencies() -> dict[str, bool]` — probes optional deps
- [ ] `VoiceVision` auto-selects backends from config or platform defaults
- [ ] Unit tests mock `platform.detect()` for each platform

## Scope

**In scope:**
- `src/voicevision/__init__.py` (main exports)
- `src/voicevision/facade.py` (VoiceVision class)
- `src/voicevision/platform.py`
- Tests in `tests/facade/`, `tests/platform/`

**Out of scope:**
- Concrete backend implementations
- Android ChaQuopy JNI bridge (stub only)

## Dependencies

- T002 (protocols, registry, config)
- T003 (dummy backends for defaults)

## Rollback

Delete `facade.py`, `platform.py`, revert `__init__.py`.

## Known Risks

- **Platform detection reliability**: `/proc/device-tree/model` may not exist on all Pis. Fallback chain needed.
- **Lazy instantiation errors**: Backend init failures should surface at access time, not construction.
- **Config vs. platform priority**: Config explicit > platform default > dummy. Document clearly.

## Notes

- Platform defaults:
  - UBUNTU/RASPBERRY_PI: ollama/llamacpp, whisper-cpp/faster-whisper, piper, moondream, opencv
  - ANDROID_TERMUX: ollama (if server), faster-whisper, piper (via termux-api?), moondream (if torch works), android camera
  - UNKNOWN: all dummy
- `check_dependencies()` used for helpful error messages: "Moondream backend selected but torch not installed. Install with `pip install voicevision[moondream]`"