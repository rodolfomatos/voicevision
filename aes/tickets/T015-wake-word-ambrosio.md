---
ticket: T015
title: Wake word "Olá Ambrósio" — activation gate for listen mode
sprint: sprint-02
priority: high
status: done
created: 2026-11-06
---

# T015 — Wake word "Olá Ambrósio" — activation gate for listen mode

## Context

T013 added `voicevision-listen`: microphone → VAD → STT (whisper.cpp) → text on stdout.
The user wants a wake word ("Olá Ambrósio") so the system only responds when
addressed, avoiding transcribing ambient conversation. This keeps the voice loop
private-by-default: nothing is sent to the LLM until the wake word is detected.

## Acceptance Criteria

- [ ] New CLI flag `--wake-word` and env var `VOICEVISION_WAKE_WORD` (default: "olá ambrósio")
- [ ] Listen mode captures continuously with VAD; each utterance is transcribed
- [ ] If a transcript contains the wake word (case-insensitive, fuzzy tolerant),
    the system signals detection and optionally passes the post-wake-word text
    to stdout for the next turn
- [ ] If no wake word is detected, the system keeps listening (no output, no LLM)
- [ ] `--seconds` fixed-duration mode still works with wake word (transcribe
    whole buffer, check for wake word)
- [ ] Error handling: wake word detection failure does not crash the loop
- [ ] Unit tests with fakes (fake VAD segments, fake whisper transcriptions)
- [ ] Integration test gated behind `@pytest.mark.integration` + env var
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)
- [ ] Does not break existing `--seconds` mode or no-wake-word behavior

## Scope

**In scope:** `src/voicevision/listen.py` (wake word logic), `tests/test_listen.py`
(new wake word tests).

**Out of scope:** LLM integration (the wake word is a gate; what happens after
detection is a separate concern), keybind changes (already in docs/VOICE_INPUT.md),
wake word training/tuning (uses existing whisper.cpp + VAD).

## Dependencies

T013 (listen.py), T012 (vad), T009 (whisper_cpp).

## Rollback

Remove wake word logic from `listen.py`; revert to plain listen mode.

## Known Risks

- **whisper.cpp latency:** wake word detection is only as fast as transcription.
  Not suitable for ultra-low-latency hotword, but acceptable for v0.1.
- **False positives/negatives:** "olá ambrósio" may be misheard as similar
  phrases. Fuzzy matching (Levenshtein-ish or substring after normalization)
  mitigates but does not eliminate.
- **Portuguese accent/whisper bias:** whisper-base is multilingual; PT-PT may
  need `--language pt`. Document this.

## Notes

- Keep import cost low: no new heavy deps. Reuse `WebrtcVadBackend` and
  `WhisperCppBackend`.
- Wake word matching: normalize (lowercase, NFD, strip combining marks,
  collapse whitespace) and check substring containment. Simple, testable,
  no new deps.
- After wake word detection, print the transcript remainder (wake word
  stripped) so the user's actual command follows immediately.
- If no wake word is heard before max_record_seconds, exits silently with
  code 0 ("wake word not detected" on stderr).

## Implementation notes (done)

Files changed:
- `src/voicevision/listen.py` — added `ListenConfig.wake_word`, `_normalize_text()`,
  `_wake_word_detected()`, `_strip_wake_word()`, `_run_wake_word()`, `--wake-word`
  CLI flag, `VOICEVISION_WAKE_WORD` env var.
- `tests/test_listen.py` — 11 new tests (normalize, detect, strip, wake word mode).

Verification:
- `pytest tests/test_listen.py` → 37 passed, 1 skipped.
- `ruff check src/voicevision/listen.py tests/test_listen.py` → clean.
- `ruff format --check` → clean.
- `mypy --strict src/voicevision/listen.py` → clean.

Pre-existing issues not caused by this change:
- `mypy --strict src` fails on vad.py/pipeline.py (pre-existing).
- `ruff check src tests` has pre-existing findings in older files.
