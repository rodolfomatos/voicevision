---
ticket: T091
title: Streaming STT Improvements - True Streaming Mode
sprint: M3-skills-intelligence
priority: high
status: todo
created: 2026-11-20
---

# T091 — Streaming STT Improvements

## Context

M3.2 from architecture audit. Current T088 implementation uses chunked processing (buffering + sentence boundary detection). True streaming would use whisper.cpp's native streaming mode (`-t` flag) or websocket-based streaming for lower latency.

## Acceptance Criteria

- [ ] Implement true streaming mode using whisper.cpp's `-t` flag (if available)
- [ ] WebSocket-based streaming endpoint for real-time transcription
- [ ] Configurable latency targets (50ms, 100ms, 200ms)
- [ ] Voice activity detection integrated with streaming (no double VAD)
- [ ] Partial results with word-level timestamps
- [ ] Language detection on streaming audio (first 1-2 seconds)
- [ ] Unit tests for streaming latency, accuracy
- [ ] Benchmark: end-to-end latency vs chunked approach

## Scope

**In scope:**
- `src/voicevision/backends/whisper_cpp.py` - enhance `transcribe_stream`
- `src/voicevision/server.py` - WebSocket `/stream` endpoint enhancement
- `tests/backends/test_whisper_cpp_streaming.py`

**Out of scope:**
- Full WebSocket server (separate service)

## Dependencies

- T088 (Streaming STT) — Done
- T086 (Adaptive VAD) — Done

## Rollback

Git revert.

## Known Risks

- whisper.cpp streaming mode may not be available in all forks
- WebSocket adds complexity to server
- Latency vs accuracy tradeoff

## Notes

Check whisper.cpp forks for streaming support:
- gguerganov/whisper.cpp - has `-t` flag for streaming
- Consider WebRTC for browser clients