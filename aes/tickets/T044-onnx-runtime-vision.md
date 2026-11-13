---
ticket: T044
title: ONNX Runtime vision path (B6)
sprint: sprint-04
priority: medium
status: done
created: 2026-11-13
completed: 2026-11-13
---

# T044 — ONNX Runtime Vision Path (B6)

## Context

Currently vision uses Moondream GGUF via llama.cpp subprocess (ADR-001/ADR-002). Piper TTS uses ONNX Runtime. Running two separate runtimes (llama.cpp + onnxruntime) is wasteful. This ticket adds an ONNX Runtime vision backend that shares the ONNX Runtime dependency with Piper, reducing dependency footprint and potentially improving performance.

## Acceptance Criteria

- [x] New module `src/voicevision/backends/onnx_vision.py` with `OnnxVisionBackend`
- [x] Uses ONNX Runtime for vision inference (shares with Piper)
- [x] Backend protocol: `available()`, `describe(image, prompt)`, `close()`
- [x] `PipelineConfig.vision_backend` can select `onnx` or `llama-cpp` (default: llama-cpp for backward compat)
- [x] `VoiceVisionService.vision` instantiates correct backend based on config
- [x] Tests cover backend with mock ONNX session
- [x] `make check` green
- [x] Document in README and CHANGELOG

## Technical Approach

1. Create `onnx_vision.py` with `OnnxVisionBackend`:
   - Load ONNX model via `onnxruntime.InferenceSession`
   - Preprocess image to model input format
   - Run inference with text prompt
   - Postprocess output to text description

2. Add `vision_backend` config option to `PipelineConfig`:
   - `"llama-cpp"` (default) — current Moondream GGUF backend
   - `"onnx"` — new ONNX Runtime backend

3. Update `VoiceVisionService.vision` to instantiate based on config

4. Add tests with mocked ONNX session

## Out of Scope

- Training or fine-tuning vision models
- Multi-model support beyond ONNX + GGUF
- GPU acceleration configuration (keep it simple, CPU by default)

## Rollback

Set `vision_backend=llama-cpp` (default) to use existing backend

## Known Risks

- ONNX Runtime is a heavy dependency (~50-100MB)
- Vision model format conversion needed (GGUF → ONNX)
- May require additional dependencies (opencv-python-headless for preprocessing)

## Implementation notes

- Added `src/voicevision/backends/onnx_vision.py` with `OnnxVisionBackend`
- ONNX Runtime inference for vision-language models (shares ONNX Runtime with Piper TTS)
- `PipelineConfig.vision_backend` config option: `llama-cpp` (default) or `onnx`
- `VoiceVisionService.vision` instantiates the correct backend based on config
- `tests/backends/test_onnx_vision.py` with mocked ONNX Runtime, PIL, and numpy
- Add `onnxruntime`, `PIL` to mypy overrides in pyproject.toml
- All 11 tests pass, quality gates pass