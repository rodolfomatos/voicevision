---
ticket: T033
title: Emotion detection on transcript
sprint: sprint-04
priority: medium
status: in-progress
created: 2026-11-09
---

# T033 — Emotion detection

## Context

Users want to know the emotional tone of the transcribed speech. This can be
done by running a small emotion classification model on the transcript text.
Since we want to keep things offline and simple, we'll use a lightweight
rule-based or small model approach that runs on the transcript after STT.

## Acceptance Criteria

- [ ] New module `src/voicevision/backends/emotion.py` with:
    - `EmotionBackend` protocol / base class
    - `SimpleEmotionBackend` implementation: keyword-based (positive/negative/
      neutral) — no external model dependency
    - `available() -> bool` returns True (always available)
- [ ] `EmotionResult` dataclass: `label: str`, `score: float` (0-1)
- [ ] `VoicePipeline.process()` and `describe_and_answer()` optionally run
  emotion detection on the final transcript
- [ ] New `emotion: bool` config option (env `VOICEVISION_EMOTION=1`)
- [ ] HTTP `/transcribe` and `/converse` return `emotion` field when enabled
- [ ] WebSocket `/stream` includes `emotion` in transcript messages
- [ ] JSON output (T025) includes `emotion` object
- [ ] Tests: backend works, integration with pipeline, HTTP/WS include field
- [ ] `make check` green

## Out of scope

- Per-utterance emotion in streaming mode (only final transcript)
- External ML model for emotion (keep it simple/rule-based for v0.2)

## Dependencies

T013 (listen), T024 (streaming LLM → TTS), T035 (HTTP), T036 (WS).

## Rollback

Delete `emotion.py`, remove `emotion` flag and fields from pipeline/HTTP/WS.