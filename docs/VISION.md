# Vision

## Problem

Anyone building a voice assistant on edge hardware rewrites the same
integration code, and usually in the wrong order.

Three failure modes recur:

1. **Fragmented interfaces.** whisper, llama.cpp, piper and moondream each
   expose a different calling convention, config format and runtime. Every
   project writes its own adapter layer, then its own bugs.
2. **In-process model runtimes.** The obvious approach — `import llama_cpp`,
   `import torch` — links a multi-hundred-megabyte native runtime into the
   caller's address space. A segfault in a quantised model kills the
   application, not just the model. Model memory is then indistinguishable from
   application memory, so "what does this use?" has no answer.
3. **Missing audio plumbing.** The hard part is rarely inference. It is voice
   activity detection, sample rates, and the gap between a cough and a
   sentence. Projects that skip VAD ship a loop that hallucinates responses to
   room noise.

## Solution

`voicevision` — a small Python library providing the voice loop as one call,
with models isolated behind a uniform interface.

- **One entry point.** `answer(audio_bytes) -> bytes`: audio in, spoken reply
  out. Every stage remains individually overridable.
- **Models are subprocesses** (ADR-002). A crashing model kills one child
  process. Model memory is separately accounted. Swapping a model does not
  restart the caller.
- **One inference runtime** (ADR-001). llama.cpp and GGUF for both the LLM and
  vision, whisper.cpp for STT, piper for TTS. One ARM64 build recipe, one
  performance profile, no `torch`.
- **`Protocol` interfaces.** Backends satisfy them structurally. A third-party
  backend needs no dependency on this package.
- **Testable with nothing installed.** Every modality has a `Dummy` backend, so
  the entire loop is covered in CI on a machine with no GPU, no models and no
  microphone.

## Value

| Property | Target | Verified by |
|----------|--------|-------------|
| Core import time | < 50 ms | NFR-1 |
| Core RSS | < 50 MB | NFR-4 (meaningful *because* models are subprocesses) |
| CI | no model download, no audio hardware | NFR-6 |
| Test coverage | ≥ 85% on `core/` and `backends/` | `make check` |
| Platform | Ubuntu 22.04+, Raspberry Pi OS | Sprint 4 |

**Success criterion:** a developer installs the library, points it at three
model files, and has a working offline voice assistant without writing a single
adapter — and can unit-test their own logic against it without owning a GPU.

## Explicitly not the goal

Android. It was considered and cut by operator decision, not by oversight:
Termux requires every binary dependency to be compiled on-device, and the audio
I/O path needs a different architecture entirely. The interfaces are designed so
that a future Android effort does not require changing `core/`.