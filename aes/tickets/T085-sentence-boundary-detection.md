---
ticket: T085
title: Sentence Boundary Detection — Port Hex's ends_sentence, spread_words, segments_from_words
sprint: M2-realtime-voice
priority: high
status: todo
created: 2026-11-17
---

# T085 — Sentence Boundary Detection

## Context

M2.1 from architecture audit. The current `_extract_sentences` in `pipeline.py` is a simplified implementation. Hex (anomalyco/hex) has robust sentence boundary detection:

- `ends_sentence()`: Detects sentence endings with proper handling of quotes, parentheses, ellipsis
- `spread_words()`: Distributes words proportionally over time intervals
- `segments_from_words()`: Reconstructs segments from word timings

## Acceptance Criteria

- [ ] Add `ends_sentence(text: str) -> bool` to `voicevision.text` module (ported from Hex)
- [ ] Add `spread_words(words, intervals) -> list` for word-to-time distribution
- [ ] Add `segments_from_words(words) -> list` for segment reconstruction
- [ ] Update `VoicePipeline._extract_sentences` to use `ends_sentence`
- [ ] Add unit tests for all three functions
- [ ] Benchmark sentence boundary accuracy vs current implementation

## Scope

**In scope:**
- `src/voicevision/text.py` (new module)
- `src/voicevision/pipeline.py` — update `_extract_sentences`
- `tests/text/test_sentence_boundary.py`

**Out of scope:**
- STT word timing integration (future)

## Dependencies

- T069-T074 (M1) — Done

## Rollback

Git revert.

## Known Risks

- Hex uses Rust; porting to Python requires careful handling of Unicode quotes
- Must handle edge cases: abbreviations (Dr., etc.), nested quotes, CJK punctuation
- Performance: `ends_sentence` called per token in streaming — must be fast

## Notes

Hex reference implementation in `crates/capture/src/transcribe.rs`:
- `ends_sentence` (line ~XX)
- `spread_words` (line ~XX)
- `segments_from_words` (line ~XX)