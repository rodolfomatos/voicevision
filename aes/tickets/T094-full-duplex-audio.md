---
ticket: T094
title: Full-Duplex Audio Support
sprint: M3-skills-intelligence
priority: high
status: todo
created: 2026-11-20
---

# T094 — Full-Duplex Audio Support

## Context

M3.5 from architecture audit. Current implementation is half-duplex (capture → process → play). Full-duplex enables simultaneous capture and playback for natural conversation with barge-in.

## Acceptance Criteria

- [ ] Simultaneous capture and playback using sounddevice duplex mode
- [ ] Echo cancellation (AEC) - WebRTC AEC or SpeexDSP
- [ ] Acoustic echo suppression
- [ ] Barge-in with <50ms interruption latency
- [ ] Configurable echo cancellation strength
- [ ] Noise suppression (RNNoise or RNNoise-ONNX)
- [ ] Automatic gain control (AGC)
- [ ] Unit tests for echo cancellation effectiveness, barge-in latency
- [ ] Benchmark: echo return loss enhancement (ERLE), barge-in latency

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