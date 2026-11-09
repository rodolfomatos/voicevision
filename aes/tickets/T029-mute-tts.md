---
ticket: T029
title: Mute TTS flag (--mute / VOICEVISION_MUTE_TTS)
sprint: sprint-04
priority: low
status: done
created: 2026-11-09
completed: 2026-11-09
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

- [x] `ListenConfig` gains `mute_tts: bool = False`
- [x] `VoicePipeline.process()` / `describe_and_answer()` respect the flag:
    when true, TTS backend is not called; the text response is still returned
- [x] `voicevision-listen` gains `--mute` flag (and `VOICEVISION_MUTE_TTS`)
- [x] The flag only affects TTS; STT, LLM, and vision still run
- [x] Tests verify TTS is not called when muted
- [x] `make check` green

## Out of scope

- Muting only specific backends
- Partial mute (e.g., mute LLM but not vision)

## Dependencies

T013 (listen mode), T024 (streaming LLM → TTS).

## Rollback

Remove `mute_tts` from `ListenConfig` and the flag handling.
## Implementation notes

- Added `mute_tts: bool = False` to `PipelineConfig` and `ListenConfig`.
- `Pipeline.process()`, `process_stream()`, `describe_and_answer()`, and the
  streaming methods all check `config.mute_tts` before calling `tts.synthesize()`.
- When muted, the pipeline still runs STT → LLM → filter, but returns empty
  bytes (or yields nothing) instead of synthesized speech.
- CLI flag `--mute` and env var `VOICEVISION_MUTE_TTS` control the setting.
- Useful for testing, logging LLM responses without audio, or chaining with
  another TTS system.
