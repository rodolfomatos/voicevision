---
ticket: T088
title: Streaming STT — Partial Transcripts
sprint: M2-realtime-voice
priority: high
status: todo
created: 2026-11-18
---

# T088 — Streaming STT (Partial Transcripts)

## Context

M2.4 from architecture audit. Current `WhisperCppBackend.transcribe_stream` buffers all audio and returns single final chunk. Need true streaming STT with partial transcripts.

## Acceptance Criteria

- [ ] `WhisperCppBackend.transcribe_stream` yields `STTChunk` with `is_final=False` for partials
- [ ] Option 1: Use `whisper.cpp` streaming mode (if available in fork)
- [ ] Option 2: Chunked processing — split audio into overlapping windows, transcribe each
- [ ] Output: `STTChunk(text, is_final, language, start_ms, end_ms)`
- [ ] Configurable chunk size (default 1.5s) and overlap (default 0.5s)
- [ ] Language detection on first chunk
- [ ] Unit tests: partial → final progression, language detection
- [ ] Benchmark: latency vs accuracy tradeoff

## Scope

**In scope:**
- `src/voicevision/backends/whisper_cpp.py` — rewrite `transcribe_stream`
- `tests/backends/test_whisper_cpp_streaming.py`

**Out of scope:**
- Real-time streaming from microphone (handled by pipeline)

## Dependencies

- T069-T074 (M1) — Done
- T085 (sentence boundary) — Done
- T086 (adaptive VAD) — Done

## Rollback

Git revert.

## Known Risks

- whisper.cpp CLI may not support true streaming; may need chunked approach
- Chunked approach adds latency and may duplicate words at boundaries
- Language detection on partial audio less accurate

## Notes

Check whisper.cpp forks for streaming support:
- `gguerganov/whisper.cpp` — may have `-t` flag for streaming
- Alternative: use `whisper.cpp` as library via `ctypes` or `whisper-cpp-python`