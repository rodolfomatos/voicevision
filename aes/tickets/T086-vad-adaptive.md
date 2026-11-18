---
ticket: T086
title: VAD Adaptativo — Port Hex's speech_islands with Adaptive Threshold
sprint: M2-realtime-voice
priority: high
status: todo
created: 2026-11-18
---

# T086 — VAD Adaptativo

## Context

M2.2 from architecture audit. Current `WebrtcVadBackend` uses fixed aggressiveness (0-3). Hex implements adaptive VAD via `speech_islands`:

- Computes noise floor from audio (percentile 10/90)
- Adapts threshold based on ambient noise
- Merges nearby speech islands (700ms gap)
- Filters digital silence (RMS < 0.0005)

## Acceptance Criteria

- [ ] Add `AdaptiveVadBackend` implementing `VADProvider` protocol
- [ ] Implement `speech_islands(audio, sample_rate) -> Generator[tuple[int, int]]`
- [ ] Noise floor estimation via percentile (10th/90th)
- [ ] Merge gap threshold: 700ms (`MERGE_GAP_MS`)
- [ ] Digital silence filter: `ISLAND_SILENCE_RMS = 0.0005`
- [ ] Configurable via `vad_adaptive: bool`, `vad_noise_percentile: int = 10`
- [ ] Benchmark: false positive/negative rate vs fixed WebRTC VAD
- [ ] Unit tests with synthetic audio (silence, speech, noise)

## Scope

**In scope:**
- `src/voicevision/backends/adaptive_vad.py` (new)
- `src/voicevision/backends/__init__.py` — export
- `tests/backends/test_adaptive_vad.py`

**Out of scope:**
- Silero VAD integration (separate ticket)

## Dependencies

- T069-T074 (M1) — Done
- T085 (sentence boundary) — Done

## Rollback

Git revert.

## Known Risks

- Adaptive threshold adds latency (need noise floor estimation window)
- May be sensitive to non-stationary noise
- Must not regress performance on clean audio

## Notes

Hex reference in `crates/capture/src/transcribe.rs`:
- `speech_islands` function
- `MERGE_GAP_MS = 700`
- `ISLAND_SILENCE_RMS = 0.0005`
- Uses percentile-based noise floor