---
ticket: T032
title: Auto language detection for STT
sprint: sprint-04
priority: high
status: in-progress
created: 2026-11-09
---

# T032 — Auto language detection

## Context

Currently the STT language is fixed via `VOICEVISION_STT_LANGUAGE` or the
`--language` flag. Users want automatic language detection: whisper.cpp can
detect the language from the audio. When enabled, the server and CLI should
auto-detect and use the detected language for transcription.

## Acceptance Criteria

- [ ] `WhisperCppBackend` gains `detect_language(wav: bytes) -> str` that
  runs whisper.cpp with `--detect-language` and parses the output
- [ ] New `language: str | Literal["auto"]` parameter on `transcribe()`:
    - `"auto"` (or `None`) triggers detection, then transcribes with detected
      language
    - explicit code skips detection
- [ ] `VoiceVisionService.transcribe()` accepts `language: str | None` and
  passes through to backend; `"auto"` becomes detection
- [ ] HTTP `/transcribe` accepts `language: "auto"` in the request body
- [ ] WebSocket `/stream` `audio` frames accept `language: "auto"`
- [ ] `voicevision-listen --language auto` enables detection
- [ ] `ListenConfig` and `VoicePipeline` thread the option through
- [ ] Detection result is included in JSON output (`detected_language`)
- [ ] Tests: detection works, explicit language still works, detection failure
  falls back to default
- [ ] `make check` green

## Out of scope

- Multi-language in a single utterance
- Language detection for the LLM (prompt language is separate)

## Dependencies

T009 (WhisperCppBackend), T035 (HTTP server), T036 (WebSocket), T017 (multi-STT).

## Rollback

Remove `detect_language`, revert `transcribe` signature, remove HTTP/WS handling.