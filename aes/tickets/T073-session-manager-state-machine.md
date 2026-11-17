---
ticket: T073
title: Session Manager + Conversation State Machine
sprint: M1-core-abstraction
priority: high
status: todo
created: 2026-11-16
---

# T073 — Session Manager + Conversation State Machine

## Context

M1.5 from architecture audit (Seção 8.1). Current `VoicePipeline.process()` is a single-turn function. Need explicit session management and state machine for multi-turn conversations, barge-in, and concurrent sessions.

## Acceptance Criteria

- [ ] `voicevision.core.sessions.SessionManager`:
  - `create_session(config: PipelineConfig, *, session_id: str | None = None) -> Session`
  - `get_session(session_id: str) -> Session | None`
  - `remove_session(session_id: str) -> None`
  - `list_sessions() -> list[SessionInfo]`
  - `cleanup_expired(max_age: timedelta) -> int`
- [ ] `Session` dataclass:
  - `session_id: str` (UUID)
  - `created_at: datetime`
  - `updated_at: datetime`
  - `config: PipelineConfig`
  - `state: ConversationState`
  - `turn_count: int`
  - `current_turn: Turn | None`
  - `history: ConversationHistory` (from existing)
  - `cancellation_token: CancellationToken` (from T074)
- [ ] `ConversationState` Enum (Seção 8.1):
  - `IDLE`, `LISTENING`, `CAPTURING`, `TRANSCRIBING`, `THINKING`, `EXECUTING`, `SPEAKING`, `INTERRUPTED`, `CANCELLED`, `ERROR`
- [ ] `Turn` dataclass:
  - `turn_id: str` (UUID)
  - `started_at: datetime`
  - `completed_at: datetime | None`
  - `state: TurnState`
  - `audio_buffer: AudioBuffer | None`
  - `transcript: str | None`
  - `llm_request: LLMRequest | None`
  - `llm_response: str | None`
  - `tts_chunks: list[bytes]`
  - `tools_invoked: list[ToolInvocation]`
- [ ] `TurnState` Enum: `PENDING`, `CAPTURING`, `TRANSCRIBING`, `THINKING`, `EXECUTING`, `SPEAKING`, `COMPLETED`, `INTERRUPTED`, `CANCELLED`, `FAILED`
- [ ] State machine transitions (validated):
  - `IDLE` + wake_word/input → `LISTENING`
  - `LISTENING` + speech → `CAPTURING`
  - `LISTENING` + cancel → `IDLE`
  - `CAPTURING` + endpoint → `TRANSCRIBING`
  - `CAPTURING` + cancel → `IDLE`
  - `TRANSCRIBING` + final → `THINKING`
  - `TRANSCRIBING` + error → `ERROR`
  - `THINKING` + tool_request → `EXECUTING`
  - `THINKING` + response → `SPEAKING`
  - `THINKING` + cancel → `CANCELLED`
  - `EXECUTING` + tool_result → `THINKING`
  - `EXECUTING` + error → `ERROR`
  - `EXECUTING` + cancel → `CANCELLED`
  - `SPEAKING` + playback_complete → `IDLE` (or `LISTENING` if continuous)
  - `SPEAKING` + user_interruption → `INTERRUPTED`
  - `SPEAKING` + cancel → `CANCELLED`
  - `INTERRUPTED` → `LISTENING` (new turn)
  - `ERROR` + recover → `IDLE`
- [ ] `SessionManager` emits events via EventBus (T072)
- [ ] Unit tests: all valid transitions, invalid transitions rejected, session lifecycle

## Scope

**In scope:**
- `src/voicevision/core/sessions.py` — new module
- `src/voicevision/core/state.py` — enums, dataclasses
- `tests/core/test_sessions.py`, `tests/core/test_state_machine.py`

**Out of scope:**
- Barge-in detection (M2.3)
- Skill execution (M3)

## Dependencies

- T072 (EventBus) — for state change events
- T074 (CancellationToken) — for session/turn cancellation
- T071 (errors) — for state transition errors

## Rollback

Git revert.

## Known Risks

- **State explosion**: Keep states minimal. Sub-states via TurnState.
- **Concurrency**: Multiple sessions must not share state. SessionManager isolates.
- **Migration**: `VoicePipeline.process()` must work with SessionManager.

## Notes

- Use `enum.StrEnum` for Python 3.11+
- State transitions raise `PipelineStateError` (from T071) on invalid
- Session persists conversation history (existing `ConversationHistory`)
- Turn correlates with EventBus `correlation_id`