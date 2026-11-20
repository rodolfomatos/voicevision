---
ticket: T090
title: Wake Word Improvements - Multiple Wake Words, Custom Models
sprint: M3-skills-intelligence
priority: high
status: todo
created: 2026-11-20
---

# T090 — Wake Word Improvements

## Context

M3.1 from architecture audit. Current wake word implementation supports multiple words via JSON config but has limitations:
- Only exact substring matching (no fuzzy matching)
- No support for custom wake word models (Porcupine, custom TF models)
- No per-wake-word sensitivity adjustment
- No wake word training/registration UI

## Acceptance Criteria

- [ ] Support for custom wake word models (Porcupine .ppn files)
- [ ] Per-wake-word sensitivity threshold configuration
- [ ] Fuzzy matching option (Levenshtein distance) for noisy environments
- [ ] Wake word confidence scoring (0.0-1.0)
- [ ] Multiple wake word models active simultaneously
- [ ] Wake word training/registration helper script
- [ ] Unit tests for fuzzy matching, confidence scoring
- [ ] Benchmark: false positive/negative rate per model

## Scope

**In scope:**
- `src/voicevision/backends/wakeword.py` (new)
- `src/voicevision/core/protocols.py` - extend WakeWordProvider
- `src/voicevision/listen.py` - integrate new wake word backend
- `scripts/wake_word_train.py` (helper)

**Out of scope:**
- Full wake word training pipeline (separate project)

## Dependencies

- T074 (CancellationToken) — Done
- T085 (sentence boundary) — Done
- T086 (adaptive VAD) — Done

## Rollback

Git revert.

## Known Risks

- Porcupine license (Apache 2.0) - acceptable
- Custom model training requires significant data
- Real-time performance on RPi with multiple models

## Notes

Consider integrating with:
- Picovoice Porcupine (Apache 2.0, supports custom keywords)
- OpenWakeWord (open source, TensorFlow Lite)
- Custom TensorFlow Lite models