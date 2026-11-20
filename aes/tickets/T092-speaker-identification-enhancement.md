---
ticket: T092
title: Speaker Identification Enhancement - pyannote.audio Integration
sprint: M3-skills-intelligence
priority: medium
status: todo
created: 2026-11-20
---

# T092 — Speaker Identification Enhancement

## Context

M3.3 from architecture audit. Current SimpleSpeakerBackend uses basic audio features (RMS, ZCR, spectral centroid) which is insufficient for reliable speaker identification. Need integration with pyannote.audio for proper speaker diarization/embedding.

## Acceptance Criteria

- [ ] Integrate pyannote.audio for speaker embedding extraction
- [ ] Speaker embedding storage and matching (cosine similarity)
- [ ] Speaker enrollment API (add/remove speakers)
- [ ] Real-time speaker identification during streaming
- [ ] Speaker diarization for multi-speaker audio
- [ ] Configurable similarity threshold
- [ ] Speaker database persistence (SQLite/JSON)
- [ ] Unit tests for enrollment, identification, diarization
- [ ] Benchmark: identification accuracy, latency

## Scope

**In scope:**
- `src/voicevision/backends/speaker_pyannote.py` (new)
- `src/voicevision/core/protocols.py` - extend SpeakerIDProvider
- `src/voicevision/listen.py` - integrate pyannote backend

**Out of scope:**
- Voice cloning/synthesis
- Speaker verification (1:1) vs identification (1:N) - both supported

## Dependencies

- T074 (CancellationToken) — Done
- T086 (Adaptive VAD) — Done
- pyannote.audio dependency (MIT license)

## Rollback

Git revert.

## Known Risks

- pyannote.audio requires PyTorch (heavy dependency)
- Model download size (~500MB)
- GPU recommended for real-time performance
- License: MIT (pyannote.audio) - compatible

## Notes

Consider lighter alternatives:
- speechbrain (also PyTorch-based)
- resemblyzer (lighter, but less accurate)
- Custom TensorFlow Lite model for edge deployment