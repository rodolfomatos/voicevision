# ADR-002 — Model backends run as subprocesses

- **Status:** Accepted (operator decision, 2026-10-09)
- **Relates to:** ADR-001 (llama.cpp / GGUF runtime)
- **Ticket:** T007

## Context

ADR-001 settles *which* runtime executes the models. This ADR settles *how the
library talks to it*: link it into the process (in-process bindings) or drive it
as a child process.

## Decision

Every model backend is a **separate long-lived OS process**. Communication is
stdin/stdout pipes, except the LLM which uses `llama-server`'s localhost HTTP
endpoint.

## Rationale

**Isolation.** A model runtime that segfaults — and llama.cpp on ARM64 with
unusual quantisations does — takes down the caller. As a subprocess it kills
one child and the caller survives. NFR-10 depends on this.

**Blob eviction.** `llama-server` already exists as a daemon with a managed
resident model. Driving its documented HTTP API means we neither reimplement
its lifecycle nor link its C++ internals into Python.

**Memory accounting.** Because models live outside our address space, "core
RSS < 50 MB" (NFR-4) is a real, checkable claim rather than a fiction that
changes with model choice.

**Alternative rejected — in-process `llama-cpp-python` bindings.** Simpler call
path, no HTTP hop, no pipe encoding. Rejected because a native crash becomes a
library-level crash with no recovery path, and because GGUF vision via
in-process bindings has no Android story we would need anyway.

**Alternative rejected — `piper-tts` Python package.** The maintained route is
the `piper` binary; the Python wrapper has been superseded upstream.

## Consequences

**Positive**
- Crash isolation and single-retry restart (FR-9)
- Model swap does not require restarting the caller
- Works unchanged on Raspberry Pi OS (Ubuntu-aarch64)
- Backends are testable by substituting a fake subprocess

**Negative**
- Pipe encoding is a real failure surface. Non-UTF-8 model output must be
  handled explicitly.
- **CLI backends cannot be kept warm (FR-7).** `whisper.cpp` and `piper` are
  one-shot programs; `communicate()` closes stdin, so a child exits when the
  call returns. Every STT and TTS call pays a process spawn (~50-100 ms). This
  was originally specified as a hard requirement ("backends must be warm") and
  turned out to be unimplementable — the fake-child harness in T008 exposed it.
  The requirement was rewritten, not the code. The LLM, where spawn cost and
  model load actually matter, is a resident HTTP daemon instead.
- Each backend needs availability probing (FR-8) to give a useful error before
  the user hits it.
- `stderr` must be drained concurrently with `stdout` or the child deadlocks
  once it fills the 64 KiB pipe buffer. `communicate()` does this; a manual pipe
  loop does not. Covered by a regression test.

## Revisit if

- Audio I/O ever needs to cross a process boundary (it currently does not).
- In-process bindings gain a documented crash-recovery story.