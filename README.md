# voicevision

> Offline multimodal AI brick: VAD → STT → LLM → filter → TTS, all models as
> subprocesses. Ubuntu 22.04+ and Raspberry Pi OS. v0.1 is the voice loop;
> vision returns in v0.2 behind unchanged interfaces.

`voicevision` is a reusable Python component — a "lego brick" — for offline
multimodal AI on the edge. It is a library, not an application: the caller owns
context, models, and audio devices. Everything runs locally, with no cloud API,
no HTTP/gRPC surface of our own, and no model runtime linked into this process.

## What it does

The v0.1 voice loop runs end to end in a single call:

```
PCM16 audio in  →  VAD (webrtcvad)  →  STT (whisper.cpp)  →
LLM (qwen3:1.7B via llama-server)  →  output filter  →  TTS (piper)  →  WAV out
```

A lighter **listen mode** is also available: microphone → STT → text on stdout,
with no LLM and no TTS. Use it with an editor hotkey to speak instead of type
(see [Voice Input](docs/VOICE_INPUT.md)).

## Design decisions (read before changing anything)

Two ADRs govern this project. Read them before touching backends, config, or
the pipeline:

| ADR | What it decides |
|-----|-----------------|
| `docs/ADR-001-backends-llamacpp.md` | llama.cpp / GGUF is the single inference runtime for LLM + vision; whisper.cpp for STT; piper (onnxruntime) for TTS. No torch, no transformers. |
| `docs/ADR-002-subprocess-backends.md` | Every model backend runs as a separate OS process. The LLM is a resident `llama-server` daemon over localhost HTTP; whisper.cpp and piper are one-shot children. |

Key consequences:

- **Crash isolation:** a segfaulting model kills one child process, not the caller.
- **Model memory is separate:** core RSS stays under 50 MB; models are counted in their own processes.
- **No `torch`, no `transformers`, no `cv2` at module scope** — heavy optional deps are lazy-imported only when used.
- **Never `shell=True`** — bandit enforces this; argv lists only.
- **Never hardcode a model path** — config or environment only (`VOICEVISION_*` prefix).
- **Models are never downloaded by this package** — operators supply paths.

## Requirements

| | |
|---|---|
| Language | Python 3.10+ |
| Target platform | Ubuntu 22.04+; Raspberry Pi OS (Ubuntu-aarch64) |
| Core runtime deps | `pydantic>=2.7`, `pydantic-settings>=2.3`, `typing-extensions>=4.10` |
| Optional runtime deps | `webrtcvad-wheels` (VAD), `sounddevice>=0.4.6` (audio capture) |
| External binaries (operator-installed) | `whisper.cpp` CLI, `llama-server`, `piper` |
| Model files | Operator-supplied; paths via `VOICEVISION_*` env vars |
| Network | None required at runtime — fully offline |

## Install

### 1. Install the library

```bash
# From a checkout of this repo
pip install -e ".[dev]"

# Or, once published:
pip install voicevision
```

The `dev` extra includes `pytest`, `ruff`, `mypy`, `bandit`, `pre-commit` for
quality gates.

### 2. Install the model backends (operator responsibility)

`voicevision` never downloads models or binaries. You must install these
yourself and point the library at them via environment variables:

| Binary | Purpose | Build / install |
|--------|---------|-----------------|
| `whisper-cli` | STT (whisper.cpp) | `git clone https://github.com/ggerganov/whisper.cpp && cmake --build build --target whisper-cli` |
| `llama-server` | LLM daemon (llama.cpp) | `cmake --build build --target llama-server` |
| `piper` | TTS | `pip install piper-tts` or build from https://github.com/rhasspy/piper |

Verify they are on `PATH`:

```bash
which whisper-cli llama-server piper
```

### 3. Obtain model files

Models are **mounted volumes, not baked into the image** (ADR-003). Place them
anywhere and reference them by env var. Example layout:

```
/models/
  ├── whisper-base.bin          # STT (~142 MB)
  ├── qwen3-1.7B.Q4_K_M.gguf    # LLM (~900 MB)
  └── voice.onnx                # TTS voice (piper)
```

Suggested sources:

- **whisper.cpp models:** https://github.com/ggerganov/whisper.cpp
  (`ggml-base.bin`, `ggml-small.bin`, etc.)
- **qwen3 GGUF:** https://huggingface.co/Qwen/Qwen3-1.7B-GGUF
- **piper voices:** https://github.com/rhasspy/piper#downloads

### 4. Optional: listen mode (voice input without LLM/TTS)

The `voicevision-listen` CLI records from the microphone, transcribes via
whisper.cpp, and prints text to stdout — no LLM, no TTS, no network. It needs
the `sounddevice` extra:

```bash
pip install -e ".[dev]"
```

Then set `VOICEVISION_STT_MODEL` (see Configuration below) and run:

```bash
voicevision-listen
# records until ~2 s of silence, then prints the transcript
```

For editor integration (OpenCode hotkey, etc.), see
[docs/VOICE_INPUT.md](docs/VOICE_INPUT.md), which includes a shell wrapper that
copies the transcript to the clipboard and a Cinnamon global-hotkey recipe.

## Quick start — worked example

### Step 0: preflight (validate the environment before anything is attempted)

```bash
export VOICEVISION_LLM_MODEL=/models/qwen3-1.7B.Q4_K_M.gguf
export VOICEVISION_STT_MODEL=/models/whisper-base.bin
export VOICEVISION_TTS_MODEL=/models/voice.onnx

python -m voicevision.preflight
```

Expected output:

```
voicevision preflight
============================================================
  OK    llama-server (llamacpp backend) at /usr/local/bin/llama-server
  OK    whisper-cli (whispercpp backend) at /usr/local/bin/whisper-cli
  OK    piper (piper backend) at /usr/local/bin/piper
  OK    llm model qwen3-1.7B.Q4_K_M.gguf (900 MB)
  OK    stt model whisper-base.bin (142 MB)
  OK    tts model voice.onnx (45 MB)
  OK    webrtcvad importable (vad)
  OK    sounddevice importable (audio capture)
============================================================
All checks passed.
```

Any `FAIL` line names the fix explicitly. Do not proceed past a failed preflight.

### Step 1: run the voice loop end to end

```python
from voicevision import VoicePipeline, PipelineConfig

config = PipelineConfig(
    # VAD
    vad_aggressiveness=2,
    vad_silence_ms=500,
    vad_max_utterance_ms=30_000,

    # STT
    stt_model="/models/whisper-base.bin",
    stt_language="en",

    # LLM
    llm_model="/models/qwen3-1.7B.Q4_K_M.gguf",
    llm_host="127.0.0.1",
    llm_port=8080,
    llm_context_size=2048,
    llm_gpu_layers=0,
    llm_threads=4,

    # TTS
    tts_model="/models/voice.onnx",
    tts_voice="",
    tts_length_scale=1.0,
)

with VoicePipeline(config) as vp:
    audio_in = open("question.wav", "rb").read()   # 16 kHz mono PCM16
    audio_out = vp.process(audio_in)                # bytes: synthesized speech
    open("answer.wav", "wb").write(audio_out)
```

`process(audio_bytes)` accepts raw PCM16 mono at 16 kHz and returns synthesized
speech as WAV bytes. Empty input returns empty bytes; an utterance with no
transcript is skipped (no wasted LLM inference on a cough).

### Step 2: stage-by-stage (override what you need)

Each stage of the pipeline is individually addressable:

```python
from voicevision import VoicePipeline, PipelineConfig

config = PipelineConfig(
    stt_model="/models/whisper-base.bin",
    llm_model="/models/qwen3-1.7B.Q4_K_M.gguf",
    tts_model="/models/voice.onnx",
)
vp = VoicePipeline(config)

# STT only
transcript = vp.stt.transcribe(audio_bytes)

# LLM only (resident daemon, starts on first call)
completion = vp.llm.complete("What is the capital of Portugal?")
print(completion.content)        # answer text
print(completion.thinking)       # reasoning trace, if any (qwen3)

# TTS only
wav = vp.tts.synthesize("Lisboa.")

vp.close()
```

### Step 3: listen mode (speak instead of type)

```bash
export VOICEVISION_STT_MODEL=/models/whisper-base.bin
voicevision-listen
# speaks until ~2 s of silence, then prints transcript to stdout
```

Or with a fixed recording duration:

```bash
voicevision-listen --seconds 5
```

See [docs/VOICE_INPUT.md](docs/VOICE_INPUT.md) for a clipboard-copy wrapper and
a Cinnamon global-hotkey setup so you can speak into OpenCode instead of typing.

## Configuration

All configuration uses pydantic-settings with the `VOICEVISION_` env prefix.
Every field has a default; nothing is required until you construct the facade.

| Env var | Default | Meaning |
|---------|---------|---------|
| `VOICEVISION_LLM_BACKEND` | `dummy` | LLM backend name (`llamacpp`, `ollama`, `dummy`) |
| `VOICEVISION_LLM_MODEL` | `""` | Model path (GGUF) — required for real runs |
| `VOICEVISION_STT_BACKEND` | `dummy` | STT backend name (`whispercpp`, `dummy`) |
| `VOICEVISION_STT_MODEL` | `""` | Model path (`.bin`) — required for real runs |
| `VOICEVISION_STT_LANGUAGE` | `en` | Transcription language |
| `VOICEVISION_TTS_BACKEND` | `dummy` | TTS backend name (`piper`, `dummy`) |
| `VOICEVISION_TTS_MODEL` | `""` | Model path (`.onnx`) |
| `VOICEVISION_VISION_BACKEND` | `dummy` | Vision backend name (v0.2) |
| `VOICEVISION_VISION_MODEL` | `""` | Vision model path (v0.2) |
| `VOICEVISION_CAMERA_BACKEND` | `dummy` | Camera backend name (v0.2) |
| `VOICEVISION_CAMERA_INDEX` | `0` | Camera device index |
| `VOICEVISION_CAMERA_RESOLUTION` | `640x480` | Capture resolution |
| `VOICEVISION_VAD_AGGRESSIVENESS` | `2` | WebRTC VAD 0–3 |
| `VOICEVISION_VAD_SILENCE_MS` | `500` | Silence to close an utterance |
| `VOICEVISION_VAD_MAX_UTTERANCE_MS` | `30000` | Runaway protection |
| `VOICEVISION_MAX_RECORD_SECONDS` | `60` | Listen-mode max recording |

### Dummy backends (no models required)

Every modality has a `Dummy` backend, so the entire loop is unit-testable on a
machine with no GPU, no models, and no microphone:

```python
from voicevision import VoicePipeline, PipelineConfig

config = PipelineConfig(  # all dummy
    llm_backend="dummy", stt_backend="dummy",
    tts_backend="dummy", vision_backend="dummy", camera_backend="dummy",
)
with VoicePipeline(config) as vp:
    out = vp.process(b"\x00" * 16000 * 2)  # 1 s of silence
```

## Project structure

```
voicevision/
├── src/voicevision/
│   ├── __init__.py          # Public API: VoicePipeline, PipelineConfig, VoiceVisionConfig, protocols, errors
│   ├── core/
│   │   ├── config.py        # VoiceVisionConfig (pydantic-settings, VOICEVISION_* prefix)
│   │   ├── protocols.py     # LLMBackend, STTBackend, TTSBackend, VisionBackend, CameraBackend
│   │   └── registry.py      # BackendRegistry — register / get / list / create by (modality, name)
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── subprocess_backend.py   # One-shot child process base (whisper.cpp, piper)
│   │   ├── resident.py             # Long-lived daemon base (llama-server)
│   │   ├── whisper_cpp.py          # STT via whisper.cpp CLI (T009)
│   │   ├── llama_cpp.py            # LLM via supervised llama-server (T010)
│   │   ├── piper.py                # TTS via piper CLI (T011)
│   │   ├── vad.py                  # VAD via webrtcvad (T012)
│   │   └── dummy.py                # Dummy backends for every modality
│   ├── listen.py               # Listen-only mode: mic → VAD → STT → stdout (T013)
│   ├── pipeline.py             # VoicePipeline: VAD → STT → LLM → filter → TTS (T013)
│   ├── preflight.py            # Deployment diagnostics: why is this not working right now
│   ├── audio.py                # WAV helpers: 16 kHz mono PCM16 contract
│   └── errors.py               # VoiceVisionError, BackendNotAvailableError, BackendExecutionError, ConfigurationError
├── tests/                      # Unit tests; every backend has Dummy siblings
├── pyproject.toml              # Package config, entry points, quality-gate settings
├── Makefile                    # make check, test, lint, format, doctor, install-voice-input
├── install-voice-input.sh      # One-command system install (sudo): backends, models, Python package
├── scripts/voicevision-listen-and-copy.sh   # Clipboard-copy wrapper for editor hotkeys
├── docs/
│   ├── VISION.md               # Problem, solution, value proposition
│   ├── REQUIREMENTS.md         # Functional + non-functional requirements (FR-1..FR-20, NFR-1..NFR-10)
│   ├── ROADMAP.md              # Sprints, backlog, Definition of Done
│   ├── ADR-001-backends-llamacpp.md   # llama.cpp / GGUF single runtime
│   ├── ADR-002-subprocess-backends.md # Every backend is a subprocess
│   ├── ADR-003-container-deployment.md # Models as volume, tini as PID 1, /dev/snd pass-through
│   ├── DESIGN.md               # Visual system (UI projects — N/A for this library)
│   ├── PERSONAS.md             # Who uses this
│   ├── QUALITY_GATES.md        # make check gates
│   ├── CHECKLIST.md            # Pre-commit / pre-release checklist
│   ├── HOSTILE_INSIGHTS.md     # Lessons from hostile analysis
│   └── VOICE_INPUT.md          # Dictation hotkey setup (editor integration)
├── aes/                        # AES project mode (kanban, tickets, sprints)
├── .aes/                       # AES hooks (pre-commit, pre-review, etc.)
├── docker/                     # Multi-stage image, compose, entrypoint (ADR-003)
└── .github/workflows/ci.yml    # CI
```

## Quality gates

Run the full gate before every commit:

```bash
make check
```

This runs docs, code, test, and lint checks:

| Gate | Command |
|------|---------|
| Docs | `make docs-check` |
| Code structure | `make code-check` |
| Tests (≥80% coverage) | `make test-check` |
| Lint (ruff + mypy --strict + bandit) | `make lint-check` |

Individual targets:

```bash
make test            # unit tests (no models, no audio hardware)
make test-integration # requires real models and audio device
make lint            # ruff, mypy --strict, bandit
make format          # ruff format
make doctor          # environment status (Python, ruff, mypy, pytest, optional deps)
make preflight       # why is this not working right now
```

## Contributing

This project follows the [AES protocol](https://github.com/rodolfomatos/aes)
(AES — Ambrósio Engineering System). Every non-trivial task goes through
reconnaissance → hostile analysis → solution proposal → implementation →
validation → critical review.

- **No `TODO:` or `FIXME:` in source** (blocked by `make code-check`).
- **No `console.log`/debug output in source.**
- **Never alter test vectors to make tests pass.**
- **Never hardcode a model path** — config or environment only.
- **Never import `torch`, `cv2`, or `sounddevice` at module scope.**
- **Never `shell=True`** — pass argv lists.

Before changing anything about backends, read
`docs/ADR-001-backends-llamacpp.md` and `docs/ADR-002-subprocess-backends.md`.

## License

MIT. See `LICENSE`.

## Version history

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-11-06 | Voice loop: VAD → STT → LLM → filter → TTS; listen mode; subprocess backends; Dummy backends; preflight; quality gates |
