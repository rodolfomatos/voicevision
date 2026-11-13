# ADR-004 — Local HTTP server

## Status

Accepted (operator decision, 2026-11-09)

## Context

The voicevision library is a reusable Python component. External processes
(editor plugins, Home Assistant, Obsidian, VS Code, Notion CLI) need a stable
interface that is not "import this Python package and know its internals".

We need a local HTTP interface that:

1. Is standard-library only (no new mandatory dependency).
2. Binds to `127.0.0.1` by default (localhost-only by design).
3. Exposes JSON endpoints: `/health`, `/transcribe`, `/describe`, `/converse`.
4. Supports optional bearer auth via `VOICEVISION_SERVER_TOKEN`.
3. Has a 10 MiB body cap to prevent memory exhaustion.

## Decision

Implement `voicevision-server` as a stdlib-only `http.server`-based HTTP
server in `src/voicevision/server.py`.

## Consequences

### Positive

- Zero new dependencies: uses `http.server`, `json`, `base64` from stdlib.
- Localhost-only by default: safe to run on any machine without worrying about
  exposing inference to the network.
- Simple JSON protocol: easy to call from any language or shell.
- Reuses the same backend classes as the CLI: behaviour and configuration stay
  identical.
- Lazy backend creation: `/health` does not spawn whisper or llama.cpp.

### Negative

- HTTP is less efficient than a raw socket for streaming audio. Mitigated by
  WebSocket endpoint (`/stream`) for streaming use cases.
- HTTP is request/response: not suitable for bidirectional streaming. Mitigated
  by `/stream` WebSocket endpoint.
- 10 MiB body cap limits audio/image size. Mitigated by `/stream` for larger
  audio streams.

### Risks

- Binder to `127.0.0.1` by default: operator must explicitly opt-in to expose
  on `0.0.0.0` via `--host`. Documented as a security consideration.
- Bearer token is optional: if not set, anyone who can reach the server can
  use it. Documented as a security consideration; operator should set
  `VOICEVISION_SERVER_TOKEN` if the server is reachable from untrusted hosts.

## Dependencies

- T035 (HTTP server)
- T009 (WhisperCppBackend)
- T010 (LlamaCppBackend)
- T011 (PiperBackend)
- T018 (MoondreamBackend / ONNXBackend)

## Rollback

Delete `src/voicevision/server.py` and remove `voicevision-server` console
script from `pyproject.toml`. The library is unaffected.