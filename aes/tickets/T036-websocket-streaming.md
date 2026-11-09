---
ticket: T036
title: WebSocket streaming endpoint for audio → transcript → tokens
sprint: sprint-03
priority: high
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T036 — WebSocket streaming

## Context

T035 exposes synchronous JSON endpoints. A client that already has a live
audio stream (an editor, a phone, a robot) should not have to buffer the whole
utterance, base64 it, and wait for one response. `/stream` upgrades to a
WebSocket, accepts audio chunks, and streams back the transcript followed by
LLM tokens as they are generated.

## Scope decision (no new dependency)

The HTTP server is deliberately standard-library only. WebSocket is therefore
implemented in `voicevision.websocket` with `hashlib`, `base64` and `struct`:
RFC 6455 handshake, masked client frames, text/binary payloads, ping/pong and
close. This is a small, local-only subset:

- no extensions (`permessage-deflate` is not negotiated)
- no fragmentation (a client that fragments gets close code 1003)
- server-to-client frames are never masked, as the RFC requires
- client frames must be masked; an unmasked frame closes with 1002

## Protocol

Client → server, one JSON object per text frame:

| Message | Meaning |
|---------|---------|
| `{"type": "audio", "audio_base64": "...", "language": "pt"}` | Append a chunk of raw PCM16 or a complete WAV |
| `{"type": "end"}` | Transcribe everything buffered, then stream the answer |
| `{"type": "reset"}` | Discard buffered audio |

Server → client, one JSON object per text frame:

| Message | Meaning |
|---------|---------|
| `{"type": "transcript", "transcript": "...", "language": "...", "transcription_ms": N}` | STT result |
| `{"type": "token", "text": "..."}` | One LLM chunk |
| `{"type": "done"}` | Generation finished; the connection stays open |
| `{"type": "error", "error": "..."}` | Recoverable failure; the connection stays open |

Ping is answered with pong; close is echoed. A protocol violation closes the
socket with the appropriate code.

## Acceptance Criteria

- [x] New module `voicevision.websocket` implementing RFC 6455 handshake and
      frame codec with the standard library only
- [x] `GET /stream` upgrades to WebSocket when the request is valid; returns
      400 without upgrade headers and 426 when `Sec-WebSocket-Version` is not 13
- [x] Handshake computes the correct `Sec-WebSocket-Accept` value
- [x] `audio` messages append raw PCM16 or WAV; `end` transcribes and streams
      `transcript` → zero or more `token` → `done`
- [x] `reset` discards buffered audio; `end` with no audio returns an `error`
- [x] Malformed JSON, unknown `type` and backend failures return a recoverable
      `error` message without dropping the connection
- [x] Unmasked client frame closes with 1002; unsupported opcode/fragmentation
      closes with 1003; payload above 1 MiB closes with 1009; invalid UTF-8
      closes with 1007
- [x] Buffered audio is capped at 10 MiB; exceeding it returns an error and
      clears the buffer
- [x] Bearer auth applies before the upgrade; a missing/wrong token gets 401
- [x] `VoiceVisionService.converse_stream()` yields LLM chunks and raises
      `ConfigurationError` when no LLM model is configured
- [x] Unit tests drive a raw socket client through handshake, audio, tokens,
      ping/pong, close and every error path
- [x] `make check` green (ruff, mypy --strict, bandit, coverage ≥ 80%)

## Out of scope

- WebSocket extensions and compression
- Fragmented messages
- Binary (non-JSON) client messages
- Concurrent conversations on one socket

## Dependencies

T035 (server, config, service).

## Rollback

Remove `/stream` routing, `websocket.py` and `tests/test_websocket.py`; the
JSON endpoints are unaffected.

## Known Risks

- A hand-written WebSocket codec is easy to get wrong. Mitigated by a strict
  subset (no extensions/fragmentation), explicit size caps, and a test client
  that exercises masking, control frames and close codes.
- Streaming tokens are only as fast as `llama-server`. The endpoint does not
  buffer the whole answer, so a slow model still shows progress.
- The server remains localhost-only by default; exposing it is the operator's
  explicit choice (see T035).

## Implementation notes

- `voicevision.websocket` exposes `accept_key`, `encode_frame`, `encode_close`,
  `read_frame` and `WebSocketConnection`. It deliberately supports only a
  strict subset: no RSV bits, no extensions, no fragmentation, masked client
  frames only, 1 MiB frame cap. Anything else closes with an RFC 6455 code.
- The handshake is handled inside `do_GET` for `/stream`; after the 101 the
  handler owns the socket until the peer closes, so `BaseHTTPRequestHandler`
  never parses another HTTP request on it.
- `VoiceVisionService.converse_stream()` reuses
  `LlamaCppBackend.complete_stream()`, so the CLI streaming path and the
  WebSocket path share one implementation.
- Recoverable errors (malformed JSON, unknown type, bad base64, backend
  failure) are `{"type":"error"}` messages and leave the socket open. Only
  protocol violations close it.
- Tests use a raw-socket client that performs the handshake and masks frames,
  so the codec is exercised in both directions without a WebSocket library.
