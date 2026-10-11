---
ticket: T011
title: PiperBackend
sprint: sprint-03
priority: high
status: done
created: 2026-10-09
---

# T011 — PiperBackend

## Context

The final stage of the loop. Simple in principle, awkward in practice: piper
writes WAV to stdout but also logs to stderr, and a long utterance produces a
long pipe read. This backend is where the deadlock risk from T007 shows up in
production.

## Acceptance Criteria

- [ ] `synthesize(text, **kwargs) -> bytes` returning WAV (FR-13)
- [ ] Drives the `piper` binary with `--model <onnx> --output_file -`
- [ ] Voice and length-scale (speed) from config
- [ ] **Long-text handling:** synthesis of a full paragraph must not deadlock.
      Test with text long enough to exceed the pipe buffer
- [ ] Verifies the returned bytes begin with a RIFF/WAVE header. Non-audio
      output (e.g. an error message that landed on stdout) must fail loudly,
      not be handed to the caller as "audio"
- [ ] Empty text returns empty bytes without spawning piper
- [ ] `available()` + `install_hint`
- [ ] Unit tests via T008's fake child
- [ ] Integration test gated behind an env var

## Scope

**In scope:** `src/voicevision/backends/piper.py` + tests

**Out of scope:** voice selection UX, streaming audio output (B1), alternative
TTS engines

## Dependencies

T007, T008

## Rollback

Delete the file and its registry entry.

## Known Risks

- **piper's stdout is not guaranteed to be pure WAV on failure.** The RIFF
  check is the guard; do not skip it because the happy path works.
- Output size scales with text length. Combined with pipe buffering this is the
  realistic deadlock trigger.
- Some piper builds buffer stdout and only flush on exit, which would defeat a
  streaming read. Verify the real binary's behaviour before assuming either way.

## Notes

This is the easiest backend to test and the easiest to get wrong. If the RIFF
check or the long-text test is skipped, the failure will surface later as
silent, intermittent silence in the speaker.