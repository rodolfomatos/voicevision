---
ticket: T031
title: Multiple wake words (simultaneous matching)
sprint: sprint-04
priority: high
status: in-progress
created: 2026-11-09
---

# T031 — Multiple wake words

## Context

T028 adds the hotword config file. This ticket ensures the wake word matching
logic correctly handles multiple words: any configured word triggers wake word
mode. The matching is case-insensitive substring search on the transcript
(after normalization).

## Acceptance Criteria

- [ ] `_transcribe_utterances` (or the wake word check helper) checks all
  configured words
- [ ] Match is case-insensitive and uses Unicode normalization (NFKC)
- [ ] Any match returns the matched word in the result (for history/logging)
- [ ] Continuous mode (T030) records which wake word was detected
- [ ] JSON output (T025) includes `wake_word` field with the matched word
- [ ] Tests cover: single word, multiple words, case variations, accent
  insensitivity, no match
- [ ] `make check` green

## Out of scope

- Fuzzy matching (Levenshtein)
- Per-word actions

## Dependencies

T028 (custom hotword file), T015 (wake word), T025 (JSON output), T030
(continuous mode).

## Rollback

Revert the matching logic to single-word check.