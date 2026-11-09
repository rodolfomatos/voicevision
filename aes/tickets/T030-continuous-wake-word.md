---
ticket: T030
title: Continuous wake word listening
sprint: sprint-03
priority: high
status: done
created: 2026-11-08
completed: 2026-11-09
---

# T030 — Continuous wake word listening

## Context

Today `voicevision-listen --wake-word` exits after the first detection. A
desktop assistant should stay resident and react every time the wake word is
spoken, without the user relaunching the command. This is the base for the
HTTP/WebSocket server (T035) and the editor integrations (T038/T039).

## Acceptance Criteria

- [x] New CLI flag `--continuous` (env `VOICEVISION_CONTINUOUS=1`)
- [x] In continuous mode the process keeps listening and prints one line (or
      one JSON object with `--json`) per detected wake word utterance
- [x] Utterances that do not contain the wake word are ignored and never
      printed or persisted
- [x] An utterance is transcribed at most once (no duplicate output while the
      VAD buffer keeps growing)
- [x] `Ctrl+C` stops the loop cleanly with exit code 0
- [x] `--continuous` without a wake word exits 2 with a clear message
- [x] Each detection is appended to the history file with `wake_word` set
- [x] `--quiet` still suppresses progress output in continuous mode
- [x] Unit tests for repeated detections, ignored utterances, no duplicates,
      Ctrl+C handling and the missing-wake-word error
- [x] `make check` green (ruff, mypy --strict, bandit, coverage ≥ 80%)

## Scope

**In scope:** `listen.py` continuous loop, CLI/env flag, tests, docs.
**Out of scope:** always-on background service/daemon (T035), multiple wake
words (T031), speaker identification (T034).

## Dependencies

T015 (wake word), T016 (pre-roll buffer), T027 (history).

## Rollback

Remove `--continuous`, `_run_wake_word_continuous()` and the dispatch branch;
single-shot wake word mode is untouched.

## Known Risks

- Unbounded memory if the VAD never closes an utterance. Mitigated by the VAD
  `max_utterance_ms` runaway guard plus a hard buffer cap.
- Duplicate transcriptions while the buffer grows. Mitigated by tracking the
  processed byte offset and trimming the buffer after each pass.
- Long-running processes may fill the history file. Retention is out of scope
  for T027 and tracked separately.

## Notes

- The loop runs until `Ctrl+C`; it deliberately ignores `max_record_seconds`,
  which stays the cap for single-shot capture.
- The rolling buffer doubles as pre-roll: audio after the last processed
  utterance is retained, so the next wake word is not clipped.

## Discovered during implementation

- **Pre-existing defect fixed:** `_transcribe_utterances()` returned
  `(None, None)` instead of `None` when no utterance matched, so single-shot
  wake word mode hit `assert transcript_result is not None` and crashed
  whenever it heard speech without the wake word. The return type is now
  `tuple[str, float] | None`, and
  `test_non_matching_utterance_does_not_crash` pins the regression.
