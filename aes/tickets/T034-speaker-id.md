---
ticket: T034
title: Speaker identification (diarization-lite)
sprint: sprint-04
priority: medium
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T034 — Speaker identification

## Context

In multi-speaker scenarios (meetings, conversations), users want to know who
spoke. Full diarization is heavy; a lightweight approach is to:
- Track voice characteristics per session (simple embedding or energy-based)
- Assign speaker labels (Speaker 1, Speaker 2, …) per utterance
- Persist a small profile per speaker for the session

For v0.2, we'll implement a session-based speaker tracker that uses simple
audio features (pitch, energy, MFCCs via a small model or rule-based) to
cluster utterances. Since this is complex, we'll start with a basic
VAD-segment-based approach: each VAD segment gets a speaker label based on
simple heuristics.

## Acceptance Criteria

- [x] New module `src/voicevision/backends/speaker.py` with:
    - `SpeakerBackend` protocol
    - `SimpleSpeakerBackend`: tracks speakers per session using
      utterance-level features (energy, duration, simple spectral features)
    - `identify(segment: AudioSegment) -> str` returns speaker label
    - `reset()` clears session
- [x] `SpeakerConfig`: `enabled: bool`, `min_utterance_duration: float`
- [x] `VoicePipeline` threads speaker identification through VAD segments
- [x] Each transcript in history/JSON/WS gets `speaker` field
- [x] HTTP `/transcribe` and `/converse` return `speaker` when enabled
- [x] WebSocket `transcript` messages include `speaker`
- [x] `voicevision-listen --speaker` enables it
- [x] Tests: backend identifies speakers, session isolation, integration
- [x] `make check` green

## Out of scope

- Cross-session speaker persistence (requires embeddings + storage)
- Real-time diarization with overlap handling
- Integration with external speaker databases

## Dependencies

T013 (listen), T016 (pre-roll), T030 (continuous), T035 (HTTP), T036 (WS).

## Rollback

Delete `speaker.py`, remove speaker fields and config.
## Implementation notes

- New module `src/voicevision/backends/speaker.py` with `SimpleSpeakerBackend`
  and `SpeakerProfile` dataclass. Session-based speaker tracking using simple
  audio features (RMS energy, zero-crossing rate, spectral centroid approximation).
- `PipelineConfig.speaker_enabled` and `ServerConfig.speaker_enabled` control
  the feature via `VOICEVISION_SPEAKER` env var.
- `VoicePipeline.detect_speaker()` method and `process()` integration.
- Speaker backend resets at the start of each `process()` call for session isolation.
- HTTP `/transcribe` returns `speaker` field when enabled.
- Simple cosine similarity matching with configurable threshold.
- Max 10 speakers per session.
