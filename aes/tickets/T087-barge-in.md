---
ticket: T087
title: Barge-in Detection + Interruption
sprint: M2-realtime-voice
priority: high
status: todo
created: 2026-11-17
---

# T087 — Barge-in Detection + Interruption

## Context

M2.3 from architecture audit. No barge-in exists currently. When user speaks during assistant response:

1. Detect new speech (VAD during playback)
2. Cancel LLM generation (if streaming)
3. Cancel TTS synthesis
4. Stop audio playback immediately
5. Preserve conversation state
6. Start new turn

## Acceptance Criteria

- [ ] Add `CancellationToken` integration to `VoicePipeline.process_stream`
- [ ] VAD monitoring during TTS playback (background task)
- [ ] On speech detection during playback:
  - Cancel LLM `generate_stream` via token
  - Cancel TTS synthesis
  - Stop audio playback (sounddevice stream abort)
  - Emit `PipelineInterrupted` event
  - Preserve partial conversation state
  - Start new turn with new speech
- [ ] Configurable: `barge_in_enabled: bool = True`, `barge_in_sensitivity: float = 0.5`
- [ ] Unit tests: interrupt during LLM, during TTS, during playback
- [ ] Integration test: full conversation with interruption

## Scope

**In scope:**
- `src/voicevision/pipeline.py` — barge-in logic in `process_stream`
- `src/voicevision/listen.py` — VAD during playback helper
- `tests/pipeline/test_barge_in.py`

**Out of scope:**
- Full-duplex audio (separate architecture)

## Dependencies

- T069-T074 (M1) — Done
- T074 (CancellationToken) — Placeholder, needs implementation
- T086 (Adaptive VAD) — Optional, improves detection

## Rollback

Git revert.

## Known Risks

- Race condition: VAD callback vs main pipeline thread
- Audio device: stopping playback cleanly on all platforms
- Partial TTS chunks already queued in sounddevice buffer
- State consistency: conversation history must not include interrupted response

## Notes

Requires `CancellationToken` from T074 to be fully implemented.