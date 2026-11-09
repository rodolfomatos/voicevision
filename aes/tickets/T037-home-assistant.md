---
ticket: T037
title: Home Assistant integration (custom component + HTTP client)
sprint: sprint-03
priority: high
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T037 — Home Assistant integration

## Context

T035/T036 gave voicevision a local HTTP/WebSocket interface. Home Assistant is
the first external consumer: a user wants to ask their house a question and
hear the answer, or have a spoken announcement transcribed, without any cloud
service.

Two deliverables:

1. `voicevision.client` — a standard-library client for the local server,
   shared by every integration (Home Assistant, VS Code, Obsidian, Notion).
2. `integrations/homeassistant/` — a Home Assistant custom component that
   registers `voicevision.converse`, `voicevision.transcribe` and
   `voicevision.describe` services and fires a `voicevision_response` event.

## Scope decision

The Home Assistant package is not a dependency of voicevision, and installing
it just to run the test suite would violate the "core imports with no optional
deps" rule. The component therefore lives outside `src/` and imports
`homeassistant` only at module import time in the integration tree. Its
presence is validated by tests that parse/compile the files, not by importing
Home Assistant.

The client itself is stdlib only (`urllib.request`, `socket`, `json`), so it
adds nothing to the package's dependency footprint.

## Acceptance Criteria

- [x] New module `voicevision.client` using only the standard library
- [x] `VoiceVisionClient.health()` returns the server status object
- [x] `VoiceVisionClient.transcribe()` sends base64 audio and returns the
      transcript payload
- [x] `VoiceVisionClient.describe()` sends base64 image + question
- [x] `VoiceVisionClient.converse()` sends text and returns the response
- [x] `VoiceVisionClient.stream()` performs a WebSocket handshake, sends
      `audio`/`end` frames and yields the decoded server messages
- [x] Bearer token is sent as `Authorization` on both HTTP and WebSocket
- [x] HTTP/WebSocket failures raise `VoiceVisionClientError` with the server's
      error message when one is available
- [x] `voicevision.websocket` gains a masked-frame encoder and a client-side
      `read_frame(..., require_mask=False)` path
- [x] `integrations/homeassistant/custom_components/voicevision/` contains a
      valid `manifest.json`, `__init__.py`, `config_flow.py`, `const.py`,
      `services.yaml` and `strings.json`
- [x] The component registers `voicevision.converse`,
      `voicevision.transcribe` and `voicevision.describe`
- [x] Unit tests cover the client against the real T035/T036 server with a
      fake service, plus validation of the integration files
- [x] `make check` green (ruff, mypy --strict, bandit, coverage ≥ 80%)

## Out of scope

- Publishing to HACS (the repository layout is HACS-compatible but no release
  action is added)
- Home Assistant Assist/STT pipeline registration
- Wake word audio capture inside Home Assistant

## Dependencies

T035 (HTTP server), T036 (WebSocket).

## Rollback

Delete `src/voicevision/client.py`, `integrations/homeassistant/` and
`tests/test_client.py`; the server is unaffected.

## Known Risks

- The component cannot be executed in this environment (Home Assistant is not
  installed). It is validated structurally; the operator must smoke-test it in
  a real Home Assistant instance.
- `urllib.request` follows redirects; the client only talks to the configured
  base URL and never to a cloud host, but a misconfigured URL is the
  operator's responsibility.

## Implementation notes

- `voicevision.client.VoiceVisionClient` is stdlib-only: `urllib.request` for
  HTTP, a raw socket + `voicevision.websocket` for `/stream`. It sends the
  bearer token on both paths and converts every failure into
  `VoiceVisionClientError`, preserving the server's JSON `error` text.
- `voicevision.websocket` now supports both directions: `encode_frame(...,
  mask=...)` / `encode_masked_frame()` for client frames and
  `read_frame(..., require_mask=False)` for unmasked server frames.
  `WebSocketConnection(mask_outgoing=True, require_mask=False)` is the client
  configuration; the server defaults are unchanged.
- The Home Assistant component lives in `integrations/homeassistant/` and is
  not imported by the test suite (Home Assistant is not a test dependency).
  `tests/test_integrations.py` compiles every integration Python file, parses
  every JSON manifest, checks the required HA files and confirms the service
  names. This catches syntax and manifest mistakes without pretending to test
  Home Assistant itself.
- The component registers its services once and stores one client per config
  entry. Blocking calls run in `hass.async_add_executor_job`; results are
  fired as `voicevision_response` with a `service` discriminator.
- The client cannot be used to test Home Assistant in CI; the operator must
  smoke-test the component in a real instance (documented in its README).
