---
ticket: T035
title: Local HTTP server exposing /transcribe, /describe, /converse
sprint: sprint-03
priority: high
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T035 — Local HTTP server

## Context

The library is currently usable only from Python or the `voicevision-listen`
CLI. Editor plugins (T038/T039), Home Assistant (T037) and any other process
need a stable local interface. A small HTTP server exposes the three core
capabilities without coupling those clients to Python internals.

## Scope decision (contract change)

`CLAUDE.md` listed "Serving over the network — no HTTP/gRPC surface of our own"
as a non-goal. The operator explicitly approved Options A/B/C, which include
this server. The non-goal is therefore superseded and updated in the same
commit. The server still respects the offline non-goal: it binds to
`127.0.0.1` by default and never calls a cloud service.

## Acceptance Criteria

- [x] New module `voicevision.server` using only the standard library
      (`http.server`, `json`, `base64`) — no new mandatory dependency
- [x] `GET /health` returns `{"status": "ok", "version": ...}`
- [x] `POST /transcribe` accepts JSON `{"audio_base64": "...", "language": "..."}`
      (raw PCM16 16 kHz mono or WAV) and returns
      `{"transcript", "language", "transcription_ms"}`
- [x] `POST /describe` accepts JSON `{"image_base64": "...", "question": "..."}`
      and returns `{"description"}`
- [x] `POST /converse` accepts JSON `{"text": "...", "max_tokens": N}` and
      returns `{"response"}`
- [x] Unknown paths return 404; wrong method returns 405; malformed JSON or
      missing fields return 400; oversized bodies (> 10 MiB) return 413;
      backend failures return 502 with a JSON `error`
- [x] Binds to `127.0.0.1` by default; `--host` is required to expose it
- [x] Optional bearer auth via `VOICEVISION_SERVER_TOKEN`; when set, requests
      without a matching `Authorization: Bearer <token>` get 401
- [x] Console script `voicevision-server` with `--host` / `--port`
- [x] Unit tests cover every endpoint, every error path, auth and size limit
- [x] `make check` green (ruff, mypy --strict, bandit, coverage ≥ 80%)

## Out of scope

- WebSocket streaming (T036)
- TLS termination — deploy behind a reverse proxy if needed
- Request queueing, rate limiting, multi-user sessions

## Dependencies

T013 (STT), T014 (vision), T010 (LLM), T024 (pipeline).

## Rollback

Delete `server.py`, the console-script entry and the tests; nothing else
imports the server.

## Known Risks

- Exposing the port on a LAN would let anyone transcribe audio and query the
  LLM. Mitigated by localhost-only default and optional bearer token.
- A blocking whisper/llama call per request limits throughput. Mitigated by
  `ThreadingHTTPServer`; heavy concurrency is out of scope.
- Base64 inflates payloads by ~33%. The 10 MiB cap bounds memory.

## Notes

- Endpoints are synchronous JSON for simplicity; streaming is T036.
- The server reuses the same backend classes as the CLI, so behaviour and
  configuration stay identical.

## Implementation notes

- Routing: `/health` is GET; `/transcribe`, `/describe` and `/converse` are
  POST. A known path with the wrong method returns 405 + `Allow`; an unknown
  path returns 404.
- `_decode_base64` rejects missing, non-string, empty and invalid base64 with
  400. Raw PCM16 is wrapped in WAV; a WAV payload is validated by
  `require_whisper_format` and never resampled. Odd-length raw PCM is a 400.
- Error mapping: client errors 400/411/413, auth 401, routing 404/405,
  `ConfigurationError` (missing model path) 500, other `VoiceVisionError`
  (backend failed/unavailable) 502, unexpected exceptions 500. No traceback is
  ever sent to a client.
- Auth is constant-time (`hmac.compare_digest`) and applies to every endpoint,
  including `/health`; a reverse proxy or a health checker must send the token
  when one is configured.
- `VoiceVisionService` caches one whisper backend per language (the language
  is part of its argv) and creates the LLM/vision backends lazily. `close()`
  shuts down the subprocess-backed backends; `MoondreamBackend` is stateless.
- Tests inject a `FakeService`, so no model files or servers are required.
  `server.py` has 100% line coverage.
