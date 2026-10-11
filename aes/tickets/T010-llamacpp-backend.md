---
ticket: T010
title: LlamaCppBackend
sprint: sprint-03
priority: high
status: done
created: 2026-10-09
---

# T010 — LlamaCppBackend

## Context

The LLM stage, and the only backend that does not speak the stdin/stdout pipe
protocol. `llama-server` is a resident daemon with a documented HTTP API;
driving it avoids reimplementing model lifecycle in Python. ADR-002 selected
this deliberately.

## Acceptance Criteria

- [ ] `generate(prompt, **kwargs) -> str` (FR-12)
- [ ] Supervises a `llama-server` subprocess: spawn on first use, keep resident
- [ ] Waits for readiness before the first call — poll `/health` with a bounded
      deadline. A fixed `sleep` is a bug.
- [ ] Model path, context size, GPU layers (`-ngl`) and threads from config
- [ ] POSTs to `/completion`; `stream: false` for v0.1
- [ ] **Thinking-token handling (FR-5):** qwen3 emits reasoning traces. The
      backend separates `content` from `thinking` in the response so the filter
      (T014) can drop the latter. Never concatenate them blindly.
- [ ] `available()` checks the binary; `install_hint` names the build
- [ ] **If the server fails to become ready, the error says so explicitly** —
      "llama-server did not become healthy within Ns" is a different problem
      from "no binary installed", and the user needs to tell them apart
- [ ] Unit tests via a fake HTTP server, no model required
- [ ] Readiness timeout is configurable and covered by a test

## Scope

**In scope:** `src/voicevision/backends/llama_cpp.py` + tests

**Out of scope:** token streaming to TTS (B1), conversation memory (B2),
vision/mmproj (v0.2)

## Dependencies

T007, T008

## Rollback

Delete the file and its registry entry.

## Known Risks

- **This backend diverges from `SubprocessBackend`'s pipe protocol.** That is
  acceptable, but do not let it sprawl: extract shared supervision (spawn,
  health, restart, close) into the base class, and let only the transport
  differ.
- `llama-server` binds a port. Port collision on a dev machine is the most
  likely "it works on my machine" failure. Make the port configurable.
- Context size affects memory. Default conservatively.

## Notes

Port allocation, timeouts and n_gpu_layers are the three knobs an operator will
actually turn. Put them in config with documented defaults, and put the reason
for each default in a comment.