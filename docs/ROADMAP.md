# Roadmap

Scope locked at v0.1 = voice loop (VAD → STT → LLM → filter → TTS), Ubuntu/RPi,
subprocess backends. Vision returns in v0.2 behind unchanged interfaces.

---

## Sprint 1 — Core foundation *(in progress)*

| ID | Task | State |
|----|------|-------|
| T002 | Protocols + registry + config | **done** |
| T006 | Unit tests for core | **done** (36 tests, 91% coverage) |
| T003 | Dummy backends (all modalities) | todo |
| T005 | CI pipeline | todo |

**Exit criteria:** core is importable, typed, tested, and green in CI.

---

## Sprint 2 — Subprocess substrate *(the hard one)*

| ID | Task | Why it matters |
|----|------|----------------|
| T007 | `SubprocessBackend` base class | Holds the process lifecycle every real backend reuses |
| T008 | Fake-subprocess test harness | T009–T011 are untestable without this |

T007 is the riskiest ticket in the project. It owns: spawn, warm reuse (FR-7),
deadline handling, stderr capture (FR-10), dead-process detection, single
restart on death (FR-9), and clean `close()`. Naive `subprocess.communicate()`
deadlocks here as soon as a child fills its stderr pipe — that failure mode is
the acceptance test.

---

## Sprint 3 — Voice backends

| ID | Task | External dependency |
|----|------|---------------------|
| T009 | `WhisperCppBackend` | `whisper.cpp` CLI |
| T010 | `LlamaCppBackend` | `llama-server` |
| T011 | `PiperBackend` | `piper` CLI |
| T012 | `WebrtcVadBackend` | `webrtcvad-wheels` |

Each ships `available()` and `install_hint` (FR-8). An operator without the
binary gets an instruction, not a `FileNotFoundError`.

---

## Sprint 4 — The loop

| ID | Task | Notes |
|----|------|-------|
| T013 | `VoicePipeline.answer()` — FR-1 | Wires VAD → STT → LLM → filter → TTS |
| T014 | Post-LLM filter — FR-5 | Strips qwen3 reasoning traces before TTS |
| T015 | `SoundDeviceCapture` / `Playback` | PortAudio, Ubuntu only |
| T016 | `VoiceVision` facade | Fail-fast config validation (FR-19) |
| T017 | Worked example + README | One end-to-end script |

**Exit criteria:** Definition of Done in `docs/REQUIREMENTS.md` fully ticked.

---

## v0.2 — Vision

| ID | Task | Blocked by |
|----|------|------------|
| T018 | `MoondreamBackend` (GGUF per ADR-001) | proven voice path |
| T019 | `CameraBackend` (OpenCV) | a real consumer |
| T020 | `describe_and_answer()` | T018 + T013 |

---

## Backlog — recorded, not scheduled

- [x] **B0** — NFR-1 import cost. **Resolved.** `VoiceVisionConfig` now loads
      lazily via PEP 562 `__getattr__`, in both `voicevision` and
      `voicevision.core`. Measured: bare `import voicevision` went from ~420 ms
      to ~4 ms; first access to `VoiceVisionConfig` costs ~180 ms and is paid
      only by callers that actually construct one. `tests/test_import_cost.py`
      asserts `pydantic` is absent from `sys.modules` after a bare import, so
      the optimisation cannot be silently reverted.
- [ ] **B1** — Streaming LLM output into TTS sentence-by-sentence (needs
      sentence-boundary detection; naive token streaming sounds broken)
- [ ] **B2** — Conversation memory across turns (currently the caller owns it)
- [ ] **B3** — Benchmark suite: TTFT, RTF, RSS per backend and quantisation
- [ ] **B4** — Android/Termux audio adapters — **separate project**, deliberately
      out of v0.1 scope
- [ ] **B5** — Model download helper CLI (operator currently installs by hand)
- [ ] **B6** — ONNX Runtime vision path, to share onnxruntime with piper
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