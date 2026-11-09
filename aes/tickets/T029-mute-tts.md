---
ticket: T029
title: Mute TTS flag (--mute / VOICEVISION_MUTE_TTS)
sprint: sprint-04
priority: low
status: in-progress
created: 2026-11-09
---

# T029 — Mute TTS

## Context

Users may want to run the full voice loop (VAD → STT → LLM → filter) but
suppress the TTS output. This is useful for:
- Testing / CI where audio output is unwanted
- Logging the LLM response without hearing it
- Chaining with another TTS system

A `--mute` flag and `VOICEVISION_MUTE_TTS=1` env var will skip the TTS step
while keeping the rest of the pipeline intact.

## Acceptance Criteria

- [ ] `ListenConfig` gains `mute_tts: bool = False`
- [ ] `VoicePipeline.process()` / `describe_and_answer()` respect the flag:
    when true, TTS backend is not called; the text response is still returned
- [ ] `voicevision-listen` gains `--mute` flag (and `VOICEVISION_MUTE_TTS`)
- [ ] The flag only affects TTS; STT, LLM, and vision still run
- [ ] Tests verify TTS is not called when muted
- [ ] `make check` green

## Out of scope

- Muting only specific backends
- Partial mute (e.g., mute LLM but not vision)

## Dependencies

T013 (listen mode), T024 (streaming LLM → TTS).

## Rollback

Remove `mute_tts` from `ListenConfig` and the flag handling.