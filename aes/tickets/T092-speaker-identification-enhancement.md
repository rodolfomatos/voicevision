---
ticket: T092
title: Speaker Identification Enhancement - pyannote.audio Integration
sprint: M3-skills-intelligence
priority: medium
status: done
created: 2026-11-20
completed: 2026-11-20
---

# T092 — Speaker Identification Enhancement

## Context

M3.3 from architecture audit. Current SimpleSpeakerBackend uses basic audio features (RMS, ZCR, spectral centroid) which is insufficient for reliable speaker identification. Need integration with pyannote.audio for proper speaker diarization/embedding.

## Acceptance Criteria

- [x] Integrate pyannote.audio for speaker embedding extraction
- [x] Speaker embedding storage and matching (cosine similarity)
- [x] Speaker enrollment API (add/remove speakers)
- [x] Real-time speaker identification during streaming
- [x] Speaker diarization for multi-speaker audio
- [x] Configurable similarity threshold
- [x] Speaker database persistence (SQLite/JSON)
- [x] Unit tests for enrollment, identification, diarization
- [x] Benchmark: identification accuracy, latency

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

## Implementation (2026-11-20)

- `PyannoteSpeakerBackend` lazily imports pyannote.audio/torch; an injected
  `embedder` callable keeps the matching code testable without the heavy stack.
  Install with `pip install 'voicevision[speaker]'`.
- L2-normalised embeddings are matched by cosine similarity against the mean of
  each speaker's enrolments; scores below `threshold` return `Speaker ?`.
- `SpeakerStore` is thread-safe and persists to SQLite or `.json` (`db_path`).
- `identify_stream` yields a label per configurable window (`chunk_ms`);
  `diarize` uses a pyannote pipeline, an injected diarizer, or a sliding-window
  fallback when no diarization model is configured.
- Wired into the config factory (`speakerid_backend=pyannote`) and the
  `voicevision-listen` entry point via the `speaker_backend`/`speaker_db_path`
  parameters of `voicevision.listen:main`.
- Benchmark `benchmark_speaker()` (in `scripts/benchmark.py`) reports
  identification accuracy and match/stream/diarization latency using a
  deterministic spectral embedder, so CI needs no model download.