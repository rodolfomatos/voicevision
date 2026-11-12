---
ticket: T042
title: Conversation memory persistence across sessions (B2)
sprint: sprint-04
priority: high
status: done
created: 2026-11-12
completed: 2026-11-12
---

# T042 — Conversation Memory Persistence Across Sessions

## Context

Currently `VoicePipeline._conversation_history` is in-memory only and lost when the pipeline is destroyed. Users want multi-turn conversations that survive process restarts.

## Acceptance Criteria

- [x] Persist conversation history to disk (JSONL format)
- [x] Configurable storage path (`VOICEVISION_CONVERSATION_PATH` or config)
- [x] Automatic load on pipeline init, save on close/context exit
- [x] TTL/expiry for old conversations (configurable, default 30 days)
- [x] Max history size limit (configurable, default 100 turns)
- [x] `VoicePipeline.load_context()` / `save_context()` public methods
- [x] Thread-safe (if multiple pipelines share storage)
- [x] Tests: persistence across pipeline recreation, TTL expiry, size limit

## Technical Approach

1. Add `conversation_path`, `conversation_ttl_days`, `max_history_size` to `PipelineConfig`
2. Add `load_context()` / `save_context()` methods to `VoicePipeline`
3. Auto-save on `close()` / `__exit__()`, auto-load on `__init__` (optional, or explicit)
4. JSONL format: one line per turn with timestamp, user_text, assistant_text
5. TTL cleanup on load/save (remove entries older than TTL)
6. Size limit enforcement on save (keep most recent N turns)

## Technical Details

Storage format (JSONL):
```json
{"timestamp": "2026-11-12T10:30:00Z", "user": "Olá", "assistant": "Olá! Como posso ajudar?"}
{"timestamp": "2026-11-12T10:30:05Z", "user": "Qual a capital do Brasil?", "assistant": "A capital é Brasília."}
```

## Out of Scope

- Encryption (future enhancement)
- Multi-user/concurrent access (single-user for now)
- Cloud sync (out of scope)

## Dependencies

- Requires `aes-preflight` for config validation
- Uses existing `PipelineConfig` pattern

## Rollback

Disable via `conversation_path=""` (default disabled)
## Implementation notes

- Added conversation persistence to `PipelineConfig` and `VoicePipeline`
- New config fields: `conversation_path`, `conversation_ttl_days`, `max_history_size`
- Added `load_context()` and `save_context()` methods with thread-safe locking
- JSONL format with timestamp, user, assistant fields
- TTL-based expiry on load (configurable days, default 30)
- Max history size limit (default 100 turns)
- Auto-save on `close()` / `__exit__`, auto-load on `__init__`
- `reset_context()` clears in-memory history and deletes saved file
- Thread-safe with `threading.Lock`
- JSONL format: `{"timestamp": "...", "user": "...", "assistant": "..."}`
- TTL applied on load (expired entries skipped)
- Max history size enforced on save (most recent N turns kept)
- All 547 tests pass
