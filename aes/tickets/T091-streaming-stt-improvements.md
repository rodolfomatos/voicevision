---
ticket: T091
title: Streaming STT Improvements - True Streaming Mode
sprint: M3-skills-intelligence
priority: high
status: done
created: 2026-11-20
completed: 2026-11-20
---

# T091 — Streaming STT Improvements

## Context

M3.2 from architecture audit. Current T088 implementation uses chunked processing (buffering + sentence boundary detection). True streaming would use whisper.cpp's native streaming mode (`-t` flag) or websocket-based streaming for lower latency.

## Acceptance Criteria

- [x] Implement true streaming mode using whisper.cpp's `-t` flag (if available)
- [x] WebSocket-based streaming endpoint for real-time transcription
- [x] Configurable latency targets (50ms, 100ms, 200ms)
- [x] Voice activity detection integrated with streaming (no double VAD)
- [x] Partial results with word-level timestamps
- [x] Language detection on streaming audio (first 1-2 seconds)
- [x] Unit tests for streaming latency, accuracy
- [x] Benchmark: end-to-end latency vs chunked approach

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

## Implementation Notes (2026-11-20)

- **True streaming**: `supports_true_streaming()` probes `--help` once per binary
  (cached). Capable binaries use a single persistent `Popen` with `-t <latency>`,
  `stderr=DEVNULL`, and a `queue.Queue`-backed stdout reader thread. Everything
  else falls back to the T088 chunked path — no silent degradation.
- **Latency targets**: `LATENCY_CHUNK_MS` maps 50/100/200 ms to chunk/overlap
  sizes of (500,150)/(1000,300)/(2000,600) ms. Explicit `chunk_size_ms` /
  `overlap_ms` always win. Unknown targets are rejected, not ignored.
- **No double VAD**: when `use_vad=True`, the caller-supplied `vad` provider is
  the single speech gate; the STT buffer only sees 30 ms frames it accepted.
- **Language**: `language="auto"` detects once from the first 1–2 s and replays
  those chunks; `language=None` uses the constructor language (no per-chunk
  detection).
- **Word timestamps**: optional `-wt` output is parsed into `WordTiming` and
  attached as `start_ms`/`end_ms` metadata on partial `STTChunk`s. Builds without
  timestamp support simply omit the field.
- **WebSocket protocol**: clients send `stream_start` → `stream_audio`* →
  `stream_end`; the server replies `stream_started`, `transcript_partial`,
  `transcript_final`, `stream_done`, or `error`.
- **Benchmarks**: `scripts/benchmark.py::benchmark_streaming` reports
  time-to-first-partial and total latency for chunked vs true streaming at each
  target. The pre-existing T089 benchmark had three unclosed `results.append(...)`
  calls that made the script unimportable; fixed as part of this ticket.
- **Tests**: 24 streaming backend tests + 5 live WebSocket streaming tests.
  Quality gates: 578 passed / 5 skipped, coverage 80.52%, ruff and mypy clean,
  `make check` green.

## Notes

Check whisper.cpp forks for streaming support:
- gguerganov/whisper.cpp - has `-t` flag for streaming
- Consider WebRTC for browser clients