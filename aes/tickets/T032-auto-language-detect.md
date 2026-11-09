---
ticket: T032
title: Auto language detection for STT
sprint: sprint-04
priority: high
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T032 — Auto language detection

## Context

Currently the STT language is fixed via `VOICEVISION_STT_LANGUAGE` or the
`--language` flag. Users want automatic language detection: whisper.cpp can
detect the language from the audio. When enabled, the server and CLI should
auto-detect and use the detected language for transcription.

## Acceptance Criteria

- [x] `WhisperCppBackend` gains `detect_language(wav: bytes) -> str` that
  runs whisper.cpp with `--detect-language` and parses the output
- [x] New `language: str | Literal["auto"]` parameter on `transcribe()`:
    - `"auto"` (or `None`) triggers detection, then transcribes with detected
      language
    - explicit code skips detection
- [x] `VoiceVisionService.transcribe()` accepts `language: str | None` and
  passes through to backend; `"auto"` becomes detection
- [x] HTTP `/transcribe` accepts `language: "auto"` in the request body
- [x] WebSocket `/stream` `audio` frames accept `language: "auto"`
- [x] `voicevision-listen --language auto` enables detection
- [x] `ListenConfig` and `VoicePipeline` thread the option through
- [x] Detection result is included in JSON output (`detected_language`)
- [x] Tests: detection works, explicit language still works, detection failure
  falls back to default
- [x] `make check` green

## Out of scope

- Multi-language in a single utterance
- Language detection for the LLM (prompt language is separate)

## Dependencies

T009 (WhisperCppBackend), T035 (HTTP server), T036 (WebSocket), T017 (multi-STT).

## Rollback

Remove `detect_language`, revert `transcribe` signature, remove HTTP/WS handling.
## Implementation notes

- Added `detect_language()` method to `WhisperCppBackend` that runs
  whisper.cpp with `--detect-language` and parses the output.
- `transcribe()` now accepts a `language` parameter that can be "auto"
  for auto-detection, a specific language code, or None (uses constructor language).
- `VoiceVisionService.transcribe()` handles "auto" by creating a temporary
  backend for detection, then transcribing with the detected language.
- HTTP `/transcribe` accepts `language: "auto"` and returns `detected_language`
  in the response when auto-detection is used.
- WebSocket `/stream` accepts `language: "auto"` in audio frames.
- CLI `voicevision-listen --language auto` enables auto-detection.
- Tests updated for new API.
