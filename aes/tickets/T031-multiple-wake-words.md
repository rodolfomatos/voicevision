---
ticket: T031
title: Multiple wake words (simultaneous matching)
sprint: sprint-04
priority: high
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T031 — Multiple wake words

## Context

T028 adds the hotword config file. This ticket ensures the wake word matching
logic correctly handles multiple words: any configured word triggers wake word
mode. The matching is case-insensitive substring search on the transcript
(after normalization).

## Acceptance Criteria

- [x] `_transcribe_utterances` (or the wake word check helper) checks all
  configured words
- [x] Match is case-insensitive and uses Unicode normalization (NFKC)
- [x] Any match returns the matched word in the result (for history/logging)
- [x] Continuous mode (T030) records which wake word was detected
- [x] JSON output (T025) includes `wake_word` field with the matched word
- [x] Tests cover: single word, multiple words, case variations, accent
  insensitivity, no match
- [x] `make check` green

## Out of scope

- Fuzzy matching (Levenshtein)
- Per-word actions

## Dependencies

T028 (custom hotword file), T015 (wake word), T025 (JSON output), T030
(continuous mode).

## Rollback

Revert the matching logic to single-word check.
## Implementation notes

Implemented as part of T028 (custom hotword file). The `wake_words_detected()`
function in `src/voicevision/core/hotwords.py` checks all configured words
with case-insensitive, accent-insensitive matching. The matched word is
returned and used throughout:
- `_run_wake_word` and `_run_wake_word_continuous` detect any configured word
- JSON output includes `wake_word` (first word) and `wake_word_detected`
- History records the specific matched word
- Continuous mode logs all configured words
