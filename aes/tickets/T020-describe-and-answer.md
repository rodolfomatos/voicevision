---
ticket: T020
title: describe_and_answer() — camera + vision + LLM pipeline
sprint: sprint-03 (v0.2)
priority: medium
status: done
created: 2026-11-07
---

# T020 — describe_and_answer() — camera + vision + LLM pipeline

## Context

v0.2 adds vision and camera behind unchanged interfaces. T014 added camera
backends (OpenCV + Playwright). T018 (MoondreamBackend) is a dependency for
vision inference. T020 wires them together: capture an image → describe via
whisper.cpp/STT or vision model → respond via LLM → synthesize via TTS.

This is the "describe and answer" flow: the user shows something to the
camera, asks a question, and gets a spoken response.

## Acceptance Criteria

- [ ] `VoicePipeline.describe_and_answer(image_data, question) -> bytes`
    — captures/uses image, transcribes/describes, generates response,
    synthesizes speech, returns WAV bytes
- [ ] `MoondreamBackend` implements `VisionBackend.describe()` via llama.cpp
    GGUF subprocess (ADR-001/ADR-002)
- [ ] Config via env vars: `VOICEVISION_VISION_BACKEND`,
    `VOICEVISION_VISION_MODEL`
- [ ] Lazy imports: `llama-cpp-python`, `pillow` never at module scope
- [ ] `available()` reports whether backend/binaries exist
- [ ] `install_hint` names install step for vision backend
- [ ] Unit tests with fakes (no real camera, no real model)
- [ ] Integration test gated behind `@pytest.mark.integration` + env var
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)
- [ ] Does NOT modify or break v0.1 voice pipeline

## Scope

**In scope:** `src/voicevision/backends/vision.py`, `src/voicevision/pipeline.py`
(describe_and_answer method), tests, config, docs updates.

**Out of scope:** v0.1 pipeline changes, GUI, network serving, Android/Termux,
real-time video streaming.

## Dependencies

T014 (camera backends), T009 (whisper_cpp), T010 (llamacpp), T011 (piper),
T013 (pipeline).

## Rollback

Remove vision backend file and describe_and_answer method; revert pipeline.

## Known Risks

- Moondream GGUF is large (~900 MB) — may not fit on RPi
- Vision + LLM + TTS chain has compound latency
- Model files not included; operator must supply

## Notes

- Follow SubprocessBackend pattern (one-shot child per call)
- VisionBackend and CameraBackend are Protocols in core/protocols.py
- core/config.py already has vision_backend, vision_model fields
- core/registry.py already registers "vision" modality
