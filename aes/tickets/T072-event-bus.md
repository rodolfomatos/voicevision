---
ticket: T072
title: In-Process Event Bus
sprint: M1-core-abstraction
priority: high
status: todo
created: 2026-11-16
---

# T072 — In-Process Event Bus

## Context

M1.4 from architecture audit. Need a simple, typed event bus for decoupling pipeline stages, enabling observability, and supporting future distributed architectures. Must support async handlers, ordering guarantees, and backpressure.

## Acceptance Criteria

- [ ] `voicevision.core.events.EventBus` class:
  - `subscribe(event_type: type[Event], handler: EventHandler) -> Subscription`
  - `publish(event: Event) -> None` — sync, fires all handlers
  - `apublish(event: Event) -> None` — async, awaits all handlers
  - `unsubscribe(subscription: Subscription) -> None`
- [ ] `Event` base class (pydantic BaseModel):
  - `event_id: UUID`
  - `event_type: str` (class name)
  - `timestamp: datetime` (UTC)
  - `session_id: str | None`
  - `turn_id: str | None`
  - `correlation_id: str | None`
  - `source: str` (module/class)
  - `schema_version: int = 1`
- [ ] Concrete events (matching Seção 10.1):
  - Audio: `AudioStarted`, `AudioFrameReceived`, `SpeechDetected`, `SpeechEnded`
  - WakeWord: `WakeWordDetected`
  - Transcription: `TranscriptionPartial`, `TranscriptionFinal`
  - Conversation: `SessionCreated`, `TurnStarted`, `TurnCompleted`, `TurnInterrupted`, `TurnCancelled`
  - LLM: `LLMRequestStarted`, `LLMTokenReceived`, `LLMRequestCompleted`, `LLMRequestFailed`
  - Skill: `SkillDiscovered`, `SkillRequested`, `SkillStarted`, `SkillCompleted`, `SkillFailed`
  - TTS: `TTSStarted`, `TTSAudioChunk`, `TTSCompleted`, `TTSCancelled`
  - Vision: `VisionFrameReceived`, `VisionAnalysisStarted`, `VisionAnalysisCompleted`
  - Memory: `MemoryStored`, `MemoryRecalled`, `MemoryDeleted`
  - Knowledge: `KnowledgeSearchStarted`, `KnowledgeSearchCompleted`
- [ ] `EventHandler` protocol: `handle(event: Event) -> None` (sync or async)
- [ ] Subscription supports: `filter: Callable[[Event], bool]`, `priority: int`
- [ ] Handler exceptions logged but don't stop other handlers
- [ ] Max queue size per event type (backpressure)
- [ ] Unit tests: publish/subscribe, async, filtering, priority, error isolation

## Scope

**In scope:**
- `src/voicevision/core/events.py` — new module
- `tests/core/test_events.py`

**Out of scope:**
- External broker (Redis, Kafka) — future if needed
- Persistence — not in M1

## Dependencies

- T071 (errors) — for error handling in handlers
- T069 (protocols) — for modality alignment

## Rollback

Git revert.

## Known Risks

- **Event explosion**: Too many event types = complexity. Start with core set.
- **Sync vs async handlers**: Mixing can cause deadlocks. Document clearly.
- **Performance**: Event bus on hot path (per audio frame) must be minimal overhead.

## Notes

- Start simple: dict of event_type -> list[handler]
- Use `asyncio.gather` with `return_exceptions=True` for async publish
- Correlation ID propagated through pipeline for tracing
- No event serialization in M1 (in-process only)