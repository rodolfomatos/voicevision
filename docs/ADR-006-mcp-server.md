# ADR-006 — MCP server (stdlib client)

## Status

Accepted (operator decision, 2026-11-09)

## Context

The HTTP server (ADR-004) and WebSocket streaming (ADR-005) expose the
voicevision API over the network. Integrations (Home Assistant, VS Code,
Obsidian, Notion) all need the same three calls: health, transcribe, describe,
converse, plus WebSocket streaming.

Instead of each integration re-implementing base64, JSON, and WebSocket
handshake, we need a shared standard-library client.

## Decision

Implement `voicevision.client` — a standard-library client for the local
HTTP/WebSocket API.

## Design constraints

1. **Standard library only.** The package's import cost is a non-functional
   requirement. An integration must not force a new dependency into a minimal
   install.
2. **Explicit failure.** Every network/HTTP/protocol failure becomes
   `VoiceVisionClientError` with the server's own message when there is one.
3. **No hidden retries.** The server is local; a caller that wants retries can
   add them with the information this module preserves.

## Client API

- `VoiceVisionClient(base_url, token, timeout)` — synchronous client
- `health()` → `{"status": "ok", "version": ...}`
- `transcribe(audio, language)` → `{"transcript": "...", "language": "..."}`
- `describe(image, question)` → `{"description": "..."}`
- `converse(text, max_tokens)` → `{"response": "..."}`
- `stream(chunks, language)` → yields `{"type": "transcript", ...}`, `{"type": "token", "text": "..."}`, `{"type": "done"}`

## Consequences

### Positive

- Zero new dependencies: stdlib `urllib.request`, `socket`, `json`.
- Explicit failures: every network/protocol failure becomes
  `VoiceVisionClientError` with the server's error message.
- No hidden retries: caller has full information to implement retries if needed.

### Negative

- Synchronous only: callers that want async must wrap in their own thread/loop.
- No retries: caller must implement retry logic if desired.

## Rollback

Delete `src/voicevision/client.py`. The server is unaffected.