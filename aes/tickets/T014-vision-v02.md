---
ticket: T014
title: Vision v0.2 — camera + vision backend (moondream via llama.cpp)
sprint: sprint-03 (v0.2)
priority: medium
status: pending
created: 2026-11-06
---

# T014 — Vision v0.2 — camera + vision backend (moondream via llama.cpp)

## Context

The voicevision CLAUDE.md explicitly defers vision and camera to v0.2:

> - Vision and camera in v0.1 — deferred to v0.2

v0.1 is the voice loop: VAD → STT (whisper.cpp) → LLM (qwen3 via llama.cpp) → output filter → TTS (piper). v0.2 adds vision and camera behind unchanged interfaces.

The protocols and registry already declare `"vision"` and `"camera"` modalities (`core/protocols.py`, `core/registry.py`, `core/config.py`), and the ADRs (`docs/ADR-001-backends-llamacpp.md`, `docs/ADR-002-subprocess-backends.md`) mandate that all model inference runs as subprocesses via GGUF/llama.cpp — never linked into this process.

This ticket is the v0.2 vision work: a camera backend (frame capture) and a vision backend (image description via moondream GGUF + llama.cpp), wired into the pipeline without breaking the v0.1 voice loop.

## Acceptance Criteria

- [ ] `CameraBackend.capture() -> bytes` — captures a single frame (JPEG/PNG)
- [ ] `CameraBackend.capture_stream() -> Iterator[bytes]` — optional frame stream
- [ ] `VisionBackend.describe(image_data, prompt?) -> str` — describes/analyzes an image
- [ ] Camera backend uses OpenCV (`opencv-python` extra) or a subprocess, never linked into this process
- [ ] Vision backend uses moondream GGUF + llama.cpp subprocess (per ADR-001/ADR-002), never torch/transformers
- [ ] Config via env vars: `VOICEVISION_CAMERA_BACKEND`, `VOICEVISION_CAMERA_INDEX`, `VOICEVISION_CAMERA_RESOLUTION`, `VOICEVISION_VISION_BACKEND`, `VOICEVISION_VISION_MODEL`
- [ ] Lazy imports: `cv2`, `llama-cpp-python`, `pillow` never at module scope (CLAUDE.md never-do)
- [ ] `available()` reports whether dependencies/binaries exist
- [ ] `install_hint` names the install step for each backend
- [ ] Unit tests with fakes (no real camera, no real model)
- [ ] Integration test gated behind `@pytest.mark.integration` + env var
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)
- [ ] Does NOT modify or break the v0.1 voice pipeline (VAD → STT → LLM → filter → TTS)

## Scope

**In scope:** `src/voicevision/backends/camera.py`, `src/voicevision/backends/vision.py` (+ moondream variant), tests, registry entries, config fields, docs updates.

**Out of scope:** v0.1 voice pipeline changes (keep untouched), GUI/application (non-goal), network serving (non-goal), Android/Termux (out of scope for v0.1), wake-word detection, real-time video streaming (v0.2+ consideration).

## Dependencies

T009 (whisper_cpp subprocess pattern), T012 (vad pattern), `opencv` extra, `moondream` extra (`llama-cpp-python`, `pillow`).

## Rollback

Delete the new backend files and their registry/config entries. The v0.1 pipeline remains intact.

## Known Risks

- **Moondream GGUF + llama.cpp** requires building llama.cpp with moondream support — verify the build flags work.
- **llama-cpp-python** is a heavy dependency; keep it optional via the `moondream` extra.
- **OpenCV** (`opencv-python`) is also heavy; keep it optional via the `opencv` extra.
- **Import cost:** `cv2` and `llama-cpp-python` must never be imported at module scope — B0 in ROADMAP.md requires core to import with zero optional deps.
- **Camera access:** `/dev/video0` or equivalent must be available; handle absence gracefully.
- **Pipeline integration:** decide where vision fits — audio in → text out, or image in → text out? Do not merge into v0.1 pipeline without a separate ticket.

## Notes

- Follow the `SubprocessBackend` pattern from `subprocess_backend.py` (one-shot child per call, no keep-alive — matches ADR-002).
- `CameraBackend` and `VisionBackend` are already declared as `runtime_checkable` Protocols in `core/protocols.py` — backends must match the signatures exactly.
- `core/config.py` already has `camera_backend`, `camera_index`, `camera_resolution`, `vision_backend`, `vision_model` fields — use them.
- `core/registry.py` already registers `"vision"` and `"camera"` in `MODALITIES`.
