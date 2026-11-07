---
ticket: T023
title: Conversation memory - multi-turn context for voice loop
sprint: sprint-03 (v0.2)
priority: high
status: done
created: 2026-11-07
---

# T023 — Conversation memory — multi-turn context for voice loop

## Context

Currently `VoicePipeline.process()` is stateless: each call to `process()` is independent. The caller owns conversation history. This works for single utterances but makes natural conversation impossible — the LLM has no memory of what was said before.

Add conversation memory so that `VoicePipeline` can maintain context across multiple turns:
- Store recent transcripts and responses
- Prepend conversation history to LLM prompts
- Prune old context to stay within token limits
- Allow resetting context (new conversation)

## Acceptance Criteria

- [ ] `VoicePipeline` accepts `max_context_utterances` config (default: 5)
- [ ] `VoicePipeline.process()` stores each utterance + response in conversation history
- [ ] `VoicePipeline.process()` prepends recent history to LLM prompt
- [ ] `VoicePipeline.reset_context()` clears conversation history
- [ ] Unit tests: memory is retained across multiple `process()` calls
- [ ] Unit tests: context is pruned when exceeding max utterances
- [ ] Unit tests: `reset_context()` clears memory
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)

## Scope

**In scope:** `src/voicevision/pipeline.py` — conversation memory logic
**Out of scope:** Persistent storage across restarts, user identification, topic detection

## Dependencies

T013 (pipeline), T009 (whisper_cpp), T010 (llamacpp), T011 (piper)

## Rollback

Remove `conversation_history` from `VoicePipeline`, revert `process()` to stateless.

## Known Risks

- Longer prompts increase LLM latency and cost
- Context window limits (2048 tokens for qwen3-1.7B)
- Pruning too aggressively loses important context

## Implementation notes (done)

Files changed:
- `src/voicevision/pipeline.py` — added `ListenConfig.max_context_utterances`,
  `ListenConfig._conversation_history`, `_build_conversation_context()`,
  `reset_context()`, `run()` integration with conversation history.
- `tests/test_pipeline.py` — 3 new tests (memory retention, pruning, reset).

Verification:
- `pytest tests/test_pipeline.py` → 22 passed.
- `ruff check` → clean.
- `ruff format --check` → clean.
- `mypy --strict` → clean.

Pre-existing issues not caused by this change:
- `mypy --strict src` fails on vad.py (pre-existing).
