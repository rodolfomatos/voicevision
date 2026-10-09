# Requirements

Scope: **v0.1 = voice loop only.** Vision and camera are v0.2+, behind unchanged interfaces.

## Functional Requirements — v0.1

### Pipeline

- **FR-1** The component exposes one call that runs the voice loop:
  `answer(audio_bytes) -> bytes` (PCM in → synthesized speech out).
  Internal stages are individually addressable for testing and for callers
  who want to override a stage.
- **FR-2** Stage order is fixed: **VAD → STT → LLM → filter → TTS**.
- **FR-3** VAD segments continuous audio into utterances. Silence longer than
  `silence_ms` closes an utterance; speech longer than `max_utterance_ms`
  forces a close (prevents runaway accumulation).
- **FR-4** An utterance that produces no transcript does not reach the LLM
  (no wasted inference on a cough or a door slam).
- **FR-5** The post-LLM filter strips reasoning traces and control tokens
  before TTS. Rationale: qwen3 emits thinking tokens that would otherwise be
  spoken aloud.

### Backends (subprocess-based)

- **FR-6** Every model backend runs as a **separate OS process**, communicating
  over stdin/stdout pipes. The library never links a model runtime into its
  own address space.
- **FR-7** **CLI backends are one-shot: one child process per call.**
  `whisper.cpp` and `piper` read input, write output, and exit; they have no
  loop mode. `communicate()` closes stdin, so a child cannot be kept alive
  between calls even in principle. The library does not pretend otherwise.
  Warm reuse applies only to the LLM daemon (FR-12), which is HTTP.
- **FR-8** Each backend exposes `available() -> bool` reporting whether its
  executable exists and is runnable, and `install_hint` naming the package
  that provides it.
- **FR-9** A child that dies mid-call is retried exactly once with a fresh
  process, then the error is surfaced. A timeout is **not** retried — it is a
  verdict about the workload, not a crash. No infinite respawn.
- **FR-10** Process stderr is captured concurrently with stdout and attached to
  any raised error, together with the command and exit code. Silent model
  failures are a bug.

### Concrete backends for v0.1

- **FR-11** `WhisperCppBackend` — drives the `whisper.cpp` CLI.
  stdin: 16 kHz mono PCM16 · stdout: transcript text.
- **FR-12** `LlamaCppBackend` — supervises a `llama-server` subprocess that it
  starts and keeps resident. Chosen over `llama-cli` because the server holds
  the model loaded between calls and exposes a documented HTTP API.
  This is the **only** warm backend in v0.1 (see FR-7).
- **FR-13** `PiperBackend` — drives the `piper` CLI.
  stdin: text · stdout: WAV bytes.
- **FR-14** `WebrtcVadBackend` — WebRTC VAD via `webrtcvad-wheels`.
  Rationale: pure C, no torch, ~1 MB wheel, 30 ms frames.
- **FR-15** `SoundDeviceCapture` — microphone capture on the target platform
  (Ubuntu). `sounddevice` (PortAudio).
- **FR-16** `SoundDevicePlayback` — speaker playback. `sounddevice`.

### Core (unchanged from T002)

- **FR-17** `Protocol` classes for each modality. Structural subtyping, no
  inheritance, so a third-party backend needs no dependency on this package.
- **FR-18** `BackendRegistry` — register / get / list / create by
  (modality, name).
- **FR-19** `VoiceVisionConfig` — pydantic-settings, env prefix
  `VOICEVISION_`, all fields defaulted, backend names validated at facade
  construction (fail fast).
- **FR-20** Lazy imports. Heavy and optional dependencies must not be imported
  at module scope.

---

## Deferred — v0.2, interface unchanged

| ID | Feature | Blocked by |
|----|---------|------------|
| F2-1 | `VisionBackend` — moondream via GGUF | ADR-001 path proven only for voice |
| F2-2 | `CameraBackend` — OpenCV capture | no consumer in v0.1 |
| F2-3 | Streaming LLM tokens to TTS | needs sentence-boundary detection |
| F2-4 | Conversation memory across turns | caller currently owns context |
| F2-5 | Android/Termux audio adapters | **out of scope** — see below |

---

## Non-Functional Requirements

| ID | Category | Requirement | How verified |
|----|----------|-------------|---------------|
| NFR-1 | Performance | Core import < 50 ms | `python -X importtime -c "import voicevision"` |
| NFR-2 | Performance | Warm LLM first-token < 500 ms on target hardware | benchmark script, `@pytest.mark.slow` |
| NFR-3 | Performance | Exactly one child per STT/TTS call; one resident daemon for the LLM | spawn-count assertions in tests |
| NFR-3b | Performance | No reaped or hung child accumulates across calls | `subprocess._active` count stable |
| NFR-4 | Memory | Core RSS < 50 MB; models are subprocesses and counted separately | `memory_profiler` |
| NFR-5 | Testability | Every backend has a `Dummy*` sibling; the whole loop is testable with no models, no audio hardware | `pytest -m "not integration"` |
| NFR-6 | Testability | CI requires no model download and no audio device | CI runs `make check` only |
| NFR-7 | Portability | Zero platform-specific imports in `voicevision/core/` | grep gate in `code-check` |
| NFR-8 | Maintainability | mypy `--strict` clean; complexity ≤ 10 per function | `make lint` |
| NFR-9 | Security | Model output reaching TTS is bounded; no `shell=True` anywhere | `bandit` |
| NFR-10 | Robustness | A crashing model process cannot take down the caller | subprocess isolation test |

---

## Constraints

| Constraint | Detail |
|------------|--------|
| Language | Python 3.10+ |
| Target platform | **Ubuntu 22.04+ only for v0.1.** Raspberry Pi OS is in scope as Ubuntu-aarch64. |
| Runtime deps (core) | `pydantic`, `pydantic-settings`, `typing-extensions`. Nothing else. |
| Optional deps | declared as extras: `webrtcvad-wheels`, `sounddevice` |
| External binaries | `whisper.cpp` CLI, `llama-server`, `piper` — installed by the operator, not by this package |
| Model management | Out of scope. Paths supplied via config. |
| Network | None required at runtime. Fully offline. |
| Android | **Explicitly out of scope for v0.1.** Termux/ChaQuopy audio I/O is a separate project. |

---

## Definition of Done — v0.1.0

- [ ] `pip install voicevision` on clean Ubuntu 22.04
- [ ] `answer(audio_bytes) -> bytes` works end to end with real models
- [ ] Whole loop testable with `Dummy*` backends, offline, no audio device
- [ ] A killed model process is respawned once and the failure surfaces clearly
- [ ] `make check` green; coverage ≥ 85% on `core/` and `backends/`
- [ ] README documents: install, model acquisition, config, one worked example
- [ ] ADR-001 and ADR-002 both `Accepted`