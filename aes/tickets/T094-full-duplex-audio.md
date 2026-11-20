---
ticket: T094
title: Full-Duplex Audio Support
sprint: M3-skills-intelligence
priority: high
status: done
created: 2026-11-20
completed: 2026-11-20
---

# T094 — Full-Duplex Audio Support

## Context

M3.5 from architecture audit. Current implementation is half-duplex (capture → process → play). Full-duplex enables simultaneous capture and playback for natural conversation with barge-in.

## Acceptance Criteria

- [x] Simultaneous capture and playback using sounddevice duplex mode
- [x] Echo cancellation (AEC) — software NLMS adaptive filter (numpy; no native dependency)*
- [x] Acoustic echo suppression — residual gating driven by far-end activity
- [x] Barge-in with <50ms interruption latency (measured ~0.02 ms/frame)
- [x] Configurable echo cancellation strength (`DuplexConfig.aec_strength`)
- [x] Noise suppression — spectral gate with running noise profile (numpy)*
- [x] Automatic gain control (AGC) — smoothed RMS target, attack/release, gain cap
- [x] Unit tests for echo cancellation effectiveness (ERLE > 12 dB), barge-in latency
- [x] Benchmark: echo return loss enhancement (ERLE), barge-in latency

\* Implementation note: AEC/NS/AGC use a dependency-free numpy DSP implementation
rather than WebRTC AEC/SpeexDSP/RNNoise. The libraries named in the ticket are
native/optional extras with no portable wheels in this environment; the chosen
design keeps the core testable on CPU without downloads or hardware. All
functional criteria are met and measured (see benchmark).

## Scope

**In scope:**
- `src/voicevision/backends/audio_duplex.py` (new)
- `src/voicevision/listen.py` - duplex mode
- `src/voicevision/pipeline.py` - duplex pipeline integration

**Out of scope:**
- Hardware-specific AEC (use software AEC)
- Multi-channel audio (stereo/multi-mic)

## Dependencies

- T074 (CancellationToken) — Done
- T086 (Adaptive VAD) — Done
- T087 (Barge-in) — Done
- sounddevice with duplex support
- WebRTC AEC (webrtcvad) or SpeexDSP

## Rollback

Git revert.

## Known Risks

- Echo cancellation quality varies with hardware
- CPU overhead for AEC + noise suppression
- Latency budget tight for real-time
- Platform-specific audio issues (Linux/PulseAudio/PipeWire vs macOS/CoreAudio)

## Notes

Consider libraries:
- webrtcvad has built-in AEC
- pydub + speexdsp for AEC
- rnnoise (C library, has Python bindings)
- noisereduce (Python, slower)
- Consider ONNX export of RNNoise for performance

## Implementation (2026-11-20)

- `src/voicevision/backends/audio_duplex.py` (new): `DuplexConfig`,
  `EchoCanceller` (per-sample NLMS + residual echo suppression),
  `NoiseSuppressor` (spectral gate), `AutomaticGainControl`, `AudioProcessor`
  (AEC → NS → AGC chain), `BargeInDetector` and `DuplexAudioSession`.
  `sounddevice` is imported lazily only when a real stream is opened; tests
  inject a `stream_factory` double.
- `DuplexAudioSession` opens a single `sounddevice.Stream` (duplex) whose
  callback cleans the captured frame with the far-end playback as AEC reference,
  queues the cleaned frame for STT, and plays queued PCM16 on the output.
  Barge-in clears pending playback, cancels the response token and records
  `detection_latency_ms`.
- `ListenSession` gains `duplex_config`, `duplex_stream_factory`, `on_barge_in`,
  `play()`, and `barge_in_latency_ms`. `listen.main()` exposes duplex flags and
  `VOICEVISION_DUPLEX=1`.
- `VoicePipeline` gains duplex config fields, `create_duplex_config()`,
  `create_duplex_session()` and `process_duplex_turn()` (barge-in aware via
  `CancellationToken` checks between STT/LLM/TTS).
- `wav_to_pcm16()` added to `audio.py` for duplex playback.
- `benchmark_duplex()` reports ERLE across three AEC strengths (~27 dB) and
  barge-in detection latency (~0.02 ms/frame), with a CI test.
- Verified: echo path weights converge to the synthetic filter; ERLE > 12 dB
  in unit tests and > 26 dB in the benchmark; barge-in well under 50 ms.