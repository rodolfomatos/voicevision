# ADR-001 — All backends route through llama.cpp / GGUF

- **Status:** Accepted (proposed, pending operator confirmation)
- **Date:** 2026-10-09
- **Ticket:** T002 (surfaced during Phase 1 hostile analysis)
- **Supersedes:** original REQUIREMENTS.md FR-13 (moondream via `moondream` + `torch`)

## Context

The original request named five technologies: qwen3:1.7B, whisper, piper, moondream,
webcam. The first instinct was to bind each to its "native" Python package.

Reverification during Phase 1 falsified two of those bindings.

## Decision

Use **llama.cpp / GGUF as the single inference runtime** for LLM and vision.
Use **whisper.cpp** for STT. Use **piper** (onnxruntime) for TTS.

| Modality | Runtime | NOT |
|----------|---------|-----|
| LLM (qwen3:1.7B) | llama.cpp, GGUF Q4_K_M | ollama (dev convenience only) |
| Vision (moondream) | llama.cpp, GGUF mmproj + Q4_K | `moondream` + torch + transformers |
| STT | whisper.cpp | openai-whisper (torch) |
| TTS | piper via onnxruntime | piper-tts (deprecated wrapper) |

## Evidence

1. **torch has no Android/Termux wheel.** Termux's pip accepts only `android_*`
   platform tags, so every binary dependency compiles from source on-device.
   Moondream via `transformers` therefore pulls a full torch build into Android.
   → Empirical, verified against termux-user-repository/pypi-wheel-builder and
   community Termux wheel-building guides.

2. **Moondream ships GGUF.** `salivosa/moondream2-gguf` provides
   `moondream2-mmproj-f16.gguf` (~868 MB) + `moondream2-q4_k.gguf` (~877 MB).
   Measured on Jetson Orin Nano 8GB: model load 1.41 s, TTFT 3.57 s,
   ~2.0 GB GPU, process RSS 259 MB (memory-mapped).
   → Empirical, third-party measurement.

3. **Moondream 2 fp16 (torch path) needs ~4.2 GB VRAM** for a 1.9B model.
   That does not fit a Pi 4/5 alongside everything else.
   Moondream 2 **0.5B** exists specifically for "mobile devices, Raspberry Pis,
   embedded cameras": 996 MiB RAM at int8, 375 MiB download at int4.
   → Empirical, vendor-published figures.

4. **Chat handler is a correctness trap.** Moondream2 GGUF requires
   `MoondreamChatHandler`; using `Llava15ChatHandler` yields zero-token or
   garbled output due to chat-template mismatch.
   → Empirical, documented in the Jetson benchmark writeup.

## Consequences

**Positive**
- One C library (`llama.cpp`) behind four modalities → one thing to compile,
  one set of ARM64 build flags, one perf profile.
- Drops torch (~2 GB) and transformers from the dependency graph.
- Android/Termux becomes plausible: prebuilt llama.cpp for Android arm64 exists.
- Vision and LLM can share a single loaded runtime and KV cache budget.

**Negative**
- Coupled to GGUF quantisation quality. q4\_k loses some accuracy vs fp16.
- No streaming-token callback parity with ollama's HTTP API for free.
- Vision encoder (mmproj) is always FP16 — no 4-bit vision encoder available.
- Audio I/O (mic + speaker) is *not* covered by llama.cpp. Still needs a
  platform-specific capture/playback layer. This is the real cross-platform
  risk, and it is **not** solved by this ADR.

## Superseded requirements

- FR-13 `MoondreamBackend` — now GGUF via llama.cpp, not torch.
- pyproject `moondream` extra — `torch`/`transformers` removed.

## Revisit if

- Moondream publishes a 4-bit vision encoder (removes the FP16 mmproj floor).
- An ONNX Runtime path for moondream matures (would let vision share
  onnxruntime with piper, at some CPU cost).