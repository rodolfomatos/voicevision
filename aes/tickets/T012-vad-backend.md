---
ticket: T012
title: WebrtcVadBackend
sprint: sprint-03
priority: high
status: todo
created: 2026-10-09
---

# T012 — WebrtcVadBackend

## Context

VAD is not an optimisation — it is what makes the loop usable. Without it,
whisper transcribes room noise and the LLM dutifully answers a door slam.

Selected `webrtcvad-wheels` over silero-vad deliberately: pure C, ~1 MB wheel,
no torch. ADR-001 removed torch from the dependency graph and this keeps it out.

## Acceptance Criteria

- [ ] Segments a PCM16 stream into utterances (FR-3)
- [ ] Config: `aggressiveness` 0–3, `silence_ms`, `max_utterance_ms`
- [ ] Operates on 30 ms frames at 8/16/32/48 kHz — reject other rates explicitly
- [ ] An utterance closes after `silence_ms` of consecutive non-speech frames
- [ ] An utterance force-closes at `max_utterance_ms` (runaway protection)
- [ ] Returns utterance boundaries, not decisions. The caller decides when to
      act — do not embed the STT call in here
- [ ] A stream with no speech yields no utterances, and yields them promptly
      (bounded buffering; do not wait for `max_utterance_ms` to report silence)
- [ ] `available()` reports whether `webrtcvad` imports
- [ ] Unit tests with synthetic PCM: silence, tone, silence+tone, tone+silence
- [ ] No audio device required

## Scope

**In scope:** `src/voicevision/backends/vad.py` + tests

**Out of scope:** the pipeline that consumes segments (T013), wake-word
detection (deliberately separate — WebRTC VAD does not do hotwords)

## Dependencies

None. Can run in parallel with T009–T011.

## Rollback

Delete the file and its registry entry.

## Known Risks

- **Aggressiveness 3 filters non-speech vocalisations** — a cough is silent,
  which is the intent, but a quiet speaker may also be filtered. Document the
  trade-off and default to 2.
- Silence detection must be *consecutive*, not cumulative. Cumulative logic
  never closes an utterance with even pauses.
- Frame alignment: a stream whose length is not a multiple of 30 ms must be
  padded or trimmed explicitly. Off-by-one here produces a persistent
  single-frame error.

## Notes

Test with generated PCM, not recordings. A 30 ms 16 kHz mono frame is 960
bytes; a one-second tone is a reliable positive and pure zeros a reliable
negative.