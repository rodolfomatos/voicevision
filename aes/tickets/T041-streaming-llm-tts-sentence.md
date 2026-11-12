---
ticket: T041
title: Streaming LLM → TTS sentence-by-sentence (B1)
sprint: sprint-04
priority: high
status: done
created: 2026-11-12
completed: 2026-11-12
---

# T041 — Streaming LLM → TTS sentence-by-sentence

## Context

Current `_stream_transcript` implementation in `VoicePipeline._stream_transcript` has a fundamental flaw: it sends the entire accumulated response to TTS on each LLM chunk, causing:
1. Repeated synthesis of already-synthesized text
2. No true sentence-by-sentence streaming
3. Increased latency and redundant computation

## Acceptance Criteria

- [x] Split LLM response into sentences using proper sentence boundary detection
- [x] Send each complete sentence to TTS as it's completed
- [x] Only synthesize new text (not re-synthesize accumulated text)
- [x] Handle edge cases: abbreviations, ellipsis, quotes, nested punctuation
- [x] Maintain conversation history correctly
- [x] Work with thinking filter (qwen3 reasoning traces)
- [x] Tests pass with sentence-by-sentence verification

## Technical Approach

1. Use a proper sentence boundary detector (not just `. ! ?`)
2. Buffer LLM chunks until a complete sentence is formed
3. Send complete sentences to TTS immediately
4. Track what's been synthesized to avoid re-synthesis
5. Handle thinking filter: filter on complete sentences only

## Out of Scope

- Word-level streaming (too granular for TTS)
- Multilingual sentence boundary detection (start with Portuguese/English)

## Dependencies

- Requires Piper TTS to be working (already fixed)
- Requires llama.cpp streaming endpoint (already working)

## Rollback Plan

Revert `_stream_transcript` to previous implementation if issues arise.

## Testing

- Unit test for sentence boundary detection
- Integration test with mock LLM streaming
- Verify TTS is called exactly once per sentence
## Implementation notes

- Added `_extract_sentences` method with proper sentence boundary detection
- Handles abbreviations (Dr., Sr., etc.), ellipsis, quotes, parentheses
- Modified `_stream_transcript` to track synthesized position and only send new sentences
- Maintains conversation history correctly
- Works with thinking filter (qwen3 reasoning traces)
- Tests pass with sentence-by-sentence verification
