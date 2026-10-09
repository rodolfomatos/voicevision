---
ticket: T009
title: WhisperCppBackend
sprint: sprint-03
priority: high
status: done
created: 2026-10-09
---

# T009 — WhisperCppBackend

## Context

First real backend. STT via the `whisper.cpp` CLI, per ADR-001. Proves the
`SubprocessBackend` contract against a real program rather than a fake.

## Acceptance Criteria

- [ ] `transcribe(audio_bytes, **kwargs) -> str` (FR-11)
- [ ] Accepts 16 kHz mono PCM16. Rejects other rates with an explicit message
      naming the actual rate — do not silently resample.
- [ ] Spawns `whisper-cli` (or `main`) with `-m <model> -f - -otxt -of -`
      language from config (`-l pt` etc.)
- [ ] Output parsing: strip the whisper.cpp progress chatter and timestamp
      headers. Returns transcript text only.
- [ ] Empty transcript returns `""`, not an error.
- [ ] `available()` reports whether the binary exists on PATH
- [ ] `install_hint` names the build step for whisper.cpp
- [ ] Unit tests via T008's fake child — no real whisper needed
- [ ] Integration test `@pytest.mark.integration` gated behind an env var

## Scope

**In scope:** `src/voicevision/backends/whisper_cpp.py` + tests

**Out of scope:** faster-whisper (different runtime, v0.2+ consideration),
VAD (T012), model download

## Dependencies

T007, T008

## Rollback

Delete the file and its registry entry.

## Known Risks

- **whisper.cpp CLI flags drift between forks and versions.** Pin the tested
  version in the README and probe flags at construction rather than assuming.
- The `-of -` output path writes a temp file in some builds; verify it does not
  litter the CWD.
- Long audio can exceed the default timeout silently.

## Notes

Whisper wants 16 kHz mono. Whatever captures audio must honour that, or this
backend becomes the place where the mistake surfaces. Do not add resampling
here — fix it at the capture layer instead.