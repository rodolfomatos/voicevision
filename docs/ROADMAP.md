# voicevision Roadmap

Scope: v0.1 = voice loop (VAD → STT → LLM → filter → TTS), Ubuntu/RPi,
subprocess backends. Vision returns in v0.2 behind unchanged interfaces.
Local HTTP server, WebSocket streaming, and MCP client added in v0.2.x.

---

## Sprint 1 — Core foundation ✅ Done

| ID | Task | State |
|----|------|-------|
| T002 | Protocols + registry + config | **done** |
| T006 | Unit tests for core | **done** (36 tests, 91% coverage) |
| T003 | Dummy backends (all modalities) | **done** |
| T005 | CI pipeline | **done** |

**Exit criteria:** core is importable, typed, tested, and green in CI. ✅

---

## Sprint 2 — Subprocess substrate ✅ Done

| ID | Task | Why it matters |
|----|------|----------------|
| T007 | `SubprocessBackend` base class | Holds the process lifecycle every real backend reuses |
| T008 | Fake-subprocess test harness | T009–T011 are untestable without this |

T007 is the riskiest ticket in the project. It owns: spawn, warm reuse (FR-7),
deadline handling, stderr capture (FR-10), dead-process detection, single
restart on death (FR-9), and clean `close()`. Naive `subprocess.communicate()`
deadlocks here as soon as a child fills its stderr pipe — that failure mode is
the acceptance test.

**Exit criteria:** subprocess lifecycle works correctly, backends can be spawned
and reaped safely, fake child enables testing without real binaries. ✅

---

## Sprint 3 — Voice backends ✅ Done

| ID | Task | External dependency |
|----|------|---------------------|
| T009 | `WhisperCppBackend` | `whisper.cpp` CLI |
| T010 | `LlamaCppBackend` | `llama-server` |
| T011 | `PiperBackend` | `piper` CLI |
| T012 | `WebrtcVadBackend` | `webrtcvad-wheels` |

Each ships `available()` and `install_hint` (FR-8). An operator without the
binary gets an instruction, not a `FileNotFoundError`.

**Exit criteria:** all four backends work with real binaries, dummy backends
work without any models. ✅

---

## Sprint 4 — The voice loop ✅ Done

| ID | Task | Notes |
|----|------|-------|
| T013 | `VoicePipeline.process()` — FR-1 | Wires VAD → STT → LLM → filter → TTS |
| T014 | Post-LLM filter — FR-5 | Strips qwen3 reasoning traces before TTS |
| T015 | SoundDevice capture / playback | PortAudio, Ubuntu only |
| T016 | `VoiceVision` facade | Fail-fast config validation (FR-19) |
| T017 | Worked example + README | One end-to-end script |

**Exit criteria:** Definition of Done in `docs/REQUIREMENTS.md` fully ticked. ✅

---

## Sprint 5 — Voice enhancements ✅ Done

| ID | Task | Notes |
|----|------|-------|
| T013 | `VoicePipeline.listen()` — microphone → STT → stdout | VAD segments audio, transcribes via whisper.cpp |
| T015 | Wake word "Olá Ambrósio" | VAD detects speech, transcribes, checks for wake word |
| T016 | Pre-roll circular buffer | Captures audio before wake word detection |
| T017 | Multiple STT models | tiny/base/small/medium/large via `VOICEVISION_STT_MODEL` |

**Exit criteria:** listen mode works with VAD segmentation, wake word detection,
and pre-roll buffer. ✅

---

## Sprint 6 — Vision v0.2 ✅ Done

| ID | Task | Status |
|----|------|--------|
| T014 | Camera backends (OpenCV + Playwright) | **done** |
| T018 | MoondreamBackend (GGUF per ADR-001) | **done** |
| T020 | `describe_and_answer()` | **done** |
| T024 | Streaming LLM → TTS | **done** |

**Exit criteria:** camera captures frames, vision backends describe images,
pipeline wires camera → vision → LLM → TTS. Streaming LLM → TTS reduces
perceived latency. ✅

---

## Sprint 7 — External interfaces & server (v0.2.x) ✅ Done

| ID | Task | Status |
|----|------|--------|
| T025 | JSON output (`--json`) | **done** |
| T026 | `--quiet` / `VOICEVISION_QUIET` | **done** |
| T027 | Transcript history | **done** |
| T028 | Custom hotword file | **done** |
| T029 | Mute TTS flag | **done** |
| T030 | Continuous wake word mode | **done** |
| T031 | Multiple wake words | **done** |
| T032 | Auto language detection | **done** |
| T033 | Emotion detection | **done** |
| T034 | Speaker identification | **done** |
| T035 | Local HTTP server | **done** |
| T036 | WebSocket streaming | **done** |
| T037 | Home Assistant integration | **done** |
| T038 | VS Code extension | **done** |
| T039 | Obsidian plugin + Notion export | **done** |

**Exit criteria:** server binds `127.0.0.1` by default, optional bearer auth,
WebSocket streaming works, integrations are structurally validated. ✅

---

## Sprint 8 — API surface & client libraries ✅ Done

| ID | Task | Status |
|----|------|--------|
| T039 | Home Assistant custom component | **done** |
| T040 | VS Code extension | **done** |
| T041 | Streaming LLM → TTS sentence-by-sentence | **done** |
| T042 | Conversation memory persistence | **done** |
| T043 | Benchmark suite (TTFT, RTF, RSS) | **done** |
| T044 | ONNX Runtime vision path | **done** |
| T045 | MCP server (stdio) | **done** |

**Exit criteria:** `make check` green, all integration tests pass, documentation
covers all new APIs. ✅

---

## v0.3.0 — Released 🎉

| Version | Date | Changes |
|---------|------|---------|
| 0.3.0 | 2026-11-13 | Local HTTP server, WebSocket streaming, MCP stdio server, custom hotword file, mute TTS flag, multiple wake words, auto language detection, emotion detection, speaker identification, streaming LLM→TTS sentence-by-sentence, conversation memory persistence, benchmark suite (TTFT, RTF, RSS), ONNX Runtime vision backend |

---

## v0.2.0 — Released 🎉

| Version | Date | Changes |
|---------|------|---------|
| 0.2.0 | 2026-11-07 | Vision backends (OpenCV + Playwright), MoondreamBackend, describe_and_answer() pipeline, conversation memory, streaming LLM → TTS |

---

## v0.1.0 — Released 🎉

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-11-06 | Voice loop: VAD → STT → LLM → filter → TTS; listen mode; subprocess backends; Dummy backends; preflight; quality gates |

---

## v0.4 — Planned (next sprint)

| ID | Task | Status |
|----|------|--------|
| — | Benchmark suite enhancements (RTF per backend, RTF trends) | planned |
| — | Conversation memory persistence across turns | planned (T042 done, needs UI/CLI) |
| — | Benchmark suite: TTFT, RTF, RSS per backend and quantisation | planned |
| — | Android/Termux audio adapters | out of scope (separate project) |

---

## Backlog — recorded, not scheduled

- [x] **B0** — NFR-1 import cost. **Resolved.** `VoiceVisionConfig` now loads
      lazily via PEP 562 `__getattr__`, in both `voicevision` and
      `voicevision.core`. Measured: bare `import voicevision` went from ~420 ms
      to ~4 ms; first access to `VoiceVisionConfig` costs ~180 ms and is paid
      only by callers that actually construct one. `tests/test_import_cost.py`
      asserts `pydantic` is absent from `sys.modules` after a bare import, so
      the optimisation cannot be silently reverted.
- [x] **B1** — Streaming LLM output into TTS sentence-by-sentence (T041)
- [x] **B2** — Conversation memory across turns (T042)
- [x] **B3** — Benchmark suite: TTFT, RTF, RSS per backend and quantisation (T043)
- [ ] **B4** — Android/Termux audio adapters — **separate project**, deliberately
      out of v0.1 scope
- [x] **B5** — Model download helper CLI (`make download-models`)
- [x] **B6** — ONNX Runtime vision path, to share onnxruntime with piper (T044)
- [x] **B7** — Container deployment. **Done.** ADR-003 records the four
      consequences (audio pass-through, models as a volume, PID 1 signal
      handling, loopback-bound `llama-server`). Delivered:
      `docker/Dockerfile` (multi-stage, buildx amd64+arm64),
      `docker/voicevision-compose.yml`, `docker/entrypoint.sh` (SIGTERM
      forwarding), and `voicevision.preflight` as a console script.
      Preflight already caught a real bug: `sounddevice` raises `OSError`, not
      `ImportError`, when PortAudio is missing, so the diagnostic was itself
      crashing on the exact failure it exists to report.

---

## Retrospectives

*Filled at end of sprint.*