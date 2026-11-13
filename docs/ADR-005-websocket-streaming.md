# ADR-005 — WebSocket streaming endpoint

## Status

Accepted (operator decision, 2026-11-09)

## Context

The HTTP server (ADR-004) is request/response: one request, one response.
This is not suitable for streaming audio to the server and receiving
transcript/token tokens as they arrive. We need a bidirectional, low-latency
streaming interface.

We need:

1. Standard-library only (no new dependency).
2. Minimal RFC 6455 subset: no extensions, no fragmentation.
3. Masked client frames only (RFC 6455 requires client→server masking).
4. 1 MiB frame cap to prevent memory exhaustion.
5. Protocol violations close with RFC 6455 close codes.

## Decision

Implement `GET /stream` WebSocket endpoint in `src/voicevision/server.py`
with a minimal RFC 6455 codec in `voicevision.websocket.py`.

## Codec subset

Supported:
- Opening handshake (RFC 6455 §4)
- Masked client frames, unmasked server frames (RFC 6455 §5)
- text/binary data frames, ping, pong, close
- Hard limits on frame size (1 MiB)

Deliberate omissions treated as protocol errors:
- No extensions
- No fragmentation
- Client frames must be masked; server frames must not be masked
- Control frames must not fragment; control frame ≤ 125 bytes

Close codes used:
- 1000: normal closure
- 1002: protocol error (unmasked client frame, masked server frame)
- 1003: unsupported data (fragmented/binary)
- 1007: invalid UTF-8 in text frame
- 1009: oversized frame (> 1 MiB)

## Client protocol

Client → Server:
- `{"type": "audio", "audio_base64": "<base64>", "language": "pt"}` — audio chunk
- `{"type": "end"}` — end of audio stream
- `{"type": "reset"}` — discard buffered audio

Server → Client:
- `{"type": "transcript", "transcript": "...", "language": "pt"}`
- `{"type": "token", "text": "Hello"}`
- `{"type": "done"}`
- `{"type": "error", "error": "..."}`

## Consequences

### Positive

- Zero new dependencies: stdlib `socket`, `json`, `base64`.
- Low latency: server streams tokens as they arrive from LLM.
- Strict protocol: violations close with RFC 6455 codes, making debugging
  easier.
- Reuses the same backends as the HTTP server.

### Negative

- WebSocket is more complex than plain HTTP for simple use cases.
- Not all HTTP clients support WebSocket.
- No built-in retry: caller must handle reconnection.

## Rollback

Remove `GET /stream` from `server.py` and `websocket.py`. The HTTP server
is unaffected.