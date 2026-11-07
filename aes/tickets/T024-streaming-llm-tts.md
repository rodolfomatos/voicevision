---
ticket: T024
title: Streaming LLM → TTS — reduce perceived latency
sprint: sprint-03 (v0.2)
priority: high
status: done
created: 2026-11-07
---

# T024 — Streaming LLM → TTS — reduce perceived latency

## Context

Currently `VoicePipeline.process()` waits for the LLM to generate the full
response before sending it to TTS. This creates a multi-second gap between the
user finishing speaking and hearing the first word of the response.

Streaming LLM → TTS sends audio chunks to TTS as soon as the LLM generates
text chunks, dramatically reducing perceived latency.

## Acceptance Criteria

- [ ] `PipelineConfig.streaming_enabled: bool = False` config option
- [ ] `VoicePipeline.process_stream()` sends audio chunks to TTS as soon as
      the LLM generates text chunks
- [ ] `VoicePipeline.process()` (non-streaming) continues to work unchanged
- [ ] Streaming disabled by default (backward compatible)
- [ ] Unit tests: streaming sends audio chunks as LLM generates them
- [ ] Unit tests: non-streaming mode unchanged
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)
- [ ] Does NOT break v0.1 voice pipeline

## Scope

**In scope:** `src/voicevision/pipeline.py` — streaming logic in `process_stream()`
**Out of scope:** WebSocket streaming, WebSocket API, real-time interruption

## Dependencies

T013 (pipeline), T009 (whisper_cpp), T010 (llamacpp), T011 (piper)

## Rollback

Set `streaming_enabled=False` (default) to disable streaming.

## Known Risks

- Audio may start before full context is known (LLM may change its mind)
- Audio chunks may overlap if TTS is slower than LLM
- Need to handle partial words at chunk boundaries gracefully

## Implementation notes (done)

Files changed:
- `src/voicevision/backends/llama_cpp.py` — added `complete_stream()` method using
  whisper.cpp streaming mode (`stream=true`). Yields text chunks as they arrive
  from the LLM server.
- `src/voicevision/pipeline.py` — added `streaming_enabled` config field,
  `_stream_transcript()` and `_process_transcript_sync()` methods, updated
  `process_stream()` to use streaming when enabled.
- `tests/test_pipeline.py` — 5 new tests (config default, config true,
  streaming orchestration, empty transcript, thinking filter).

Verification:
- `pytest tests/test_pipeline.py` → 25 passed
- `pytest tests/test_*` (all) → 305 passed, 6 skipped
- `ruff check src/voicevision tests` → clean
- `ruff format --check src/voicevision tests` → clean
- `mypy --strict src/voicevision/backends/llama_cpp.py src/voicevision/pipeline.py` → clean

Pre-existing issues not caused by this change:
- `mypy --strict src` fails on vad.py (pre-existing - webrtcvad not installed)
