---
ticket: T034
title: Speaker identification (diarization-lite)
sprint: sprint-04
priority: medium
status: in-progress
created: 2026-11-09
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

- [ ] New module `src/voicevision/backends/speaker.py` with:
    - `SpeakerBackend` protocol
    - `SimpleSpeakerBackend`: tracks speakers per session using
      utterance-level features (energy, duration, simple spectral features)
    - `identify(segment: AudioSegment) -> str` returns speaker label
    - `reset()` clears session
- [ ] `SpeakerConfig`: `enabled: bool`, `min_utterance_duration: float`
- [ ] `VoicePipeline` threads speaker identification through VAD segments
- [ ] Each transcript in history/JSON/WS gets `speaker` field
- [ ] HTTP `/transcribe` and `/converse` return `speaker` when enabled
- [ ] WebSocket `transcript` messages include `speaker`
- [ ] `voicevision-listen --speaker` enables it
- [ ] Tests: backend identifies speakers, session isolation, integration
- [ ] `make check` green

## Out of scope

- Cross-session speaker persistence (requires embeddings + storage)
- Real-time diarization with overlap handling
- Integration with external speaker databases

## Dependencies

T013 (listen), T016 (pre-roll), T030 (continuous), T035 (HTTP), T036 (WS).

## Rollback

Delete `speaker.py`, remove speaker fields and config.