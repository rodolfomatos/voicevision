# voicevision

> Offline multimodal AI brick: VAD → STT → LLM → filter → TTS, all models as
> subprocesses. Ubuntu 22.04+ and Raspberry Pi OS. v0.1 is the voice loop;
> vision returns in v0.2 behind unchanged interfaces.

`voicevision` is a reusable Python component — a "lego brick" — for offline
multimodal AI on the edge. It is a library, not an application: the caller owns
context, models, and audio devices. Everything runs locally, with no cloud API,
no HTTP/gRPC surface of our own, and no model runtime linked into this process.

---

# 🚀 Quick Start

## 1. Clone and install

```bash
git clone https://github.com/rodolfomatos/voicevision.git
cd voicevision
pip install -e ".[dev]"
```

## 2. Install system dependencies (requires sudo)

```bash
make install-voice-input
```

This installs: `xclip`, `cmake`, `build-essential`, `git`, `curl`, `python3-pip`,
`whisper.cpp` CLI, `llama-server`, `piper`, and the `voicevision-listen-and-copy`
wrapper script.

## 3. Download models

Models are **not included** — you must download them yourself:

```bash
# whisper.cpp STT model (~142 MB)
curl -L -o /models/whisper-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

# LLM model (Qwen3 1.7B, ~1.7 GB)
curl -L -o /models/Qwen3-1.7B-Q8_0.gguf \
  https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q8_0.gguf

# piper TTS voice model (~2 MB)
curl -L -o /models/voice.onnx \
  https://huggingface.co/rhasspy/piper-voices/raw/master/en/en_US/kokoro/x_low/en_US-kokoro-x_low.onnx

# moondream vision model (2.8 GB text model)
curl -L -o /models/moondream2-text-model-f16.gguf \
  https://huggingface.co/moondream/moondream2-gguf/resolve/main/moondream2-text-model-f16.gguf

# moondream vision projection model (910 MB)
curl -L -o /models/moondream2-mmproj-f16.gguf \
  https://huggingface.co/moondream/moondream2-gguf/resolve/main/moondream2-mmproj-f16.gguf
```

## 4. Configure environment variables

Create a `.env` file:

```bash
VOICEVISION_STT_MODEL=/models/whisper-base.bin
VOICEVISION_LLM_MODEL=/models/Qwen3-1.7B.Q8_0.gguf
VOICEVISION_TTS_MODEL=/models/voice.onnx
VOICEVISION_VISION_MODEL=/models/moondream2-text-model-f16.gguf
VOICEVISION_STT_LANGUAGE=pt
```

Then `source .env` or add to your `~/.bashrc`.

## 5. Start llama-server (for LLM + vision)

```bash
/opt/voicevision/llama-server -m /models/Qwen3-1.7B-Q8_0.gguf --port 8080 -c 2048
```

In another terminal, start whisper.cpp server if needed:
```bash
/opt/voicevision/whisper-server -m /models/whisper-base.bin --port 8082
```

---

# 🎤 Voice Input (listen mode)

The `voicevision-listen` command captures audio from your microphone,
transcribes it via whisper.cpp, and prints the text to stdout.

## Basic usage

```bash
# Record for 5 seconds, transcribe, print text
python -m voicevision.listen --seconds 5

# With wake word detection (default 5 second timeout)
VOICEVISION_STT_MODEL=/models/whisper-base.bin \
voicevision-listen --wake-word "Olá Ambrósio"
```

## With clipboard (for OpenCode / any editor)

```bash
voicevision-listen-and-copy
```

This records 5 seconds, transcribes, and copies the result to your clipboard.
Then paste with `Ctrl+V` into any application.

## Keybind setup (Cinnamon desktop)

System Settings → Keyboard → Shortcuts → Custom Shortcuts → +

| Field | Value |
|-------|-------|
| Name | Voice → Text |
| Command | `~/.local/bin/voicevision-listen-and-copy` |
| Shortcut | `F9` (or your choice) |

See `docs/VOICE_INPUT.md` for full documentation.

---

# 📦 Project Documentation

| File | Description |
|------|-------------|
| `docs/VISION.md` | Problem, solution, value proposition |
| `docs/REQUIREMENTS.md` | Functional + non-functional requirements |
| `docs/ROADMAP.md` | Sprints, backlog, Definition of Done |
| `docs/ADR-001-backends-llamacpp.md` | llama.cpp / GGUF single runtime decision |
| `docs/ADR-002-subprocess-backends.md` | Subprocess backend decision |
| `docs/ADR-003-container-deployment.md` | Containerized deployment decision |
| `docs/QUALITY_GATES.md` | Quality gate configuration |
| `docs/CHECKLIST.md` | Pre-commit / pre-release checklist |
| `docs/HOSTILE_INSIGHTS.md` | Lessons from hostile analysis |
| `docs/VOICE_INPUT.md` | Dictation hotkey setup (editor integration) |

---

# 🏗️ Project Structure

```
voicevision/
├── src/voicevision/
│   ├── __init__.py          # Public API
│   ├── core/
│   │   ├── config.py        # VoiceVisionConfig (env vars)
│   │   ├── protocols.py     # Protocol interfaces
│   │   ├── registry.py      # Backend registry
│   │   └── __init__.py
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── subprocess_backend.py   # Subprocess base class
│   │   ├── resident.py            # Daemon backend base
│   │   ├── whisper_cpp.py         # STT via whisper.cpp CLI
│   │   ├── llama_cpp.py           # LLM via llama-server
│   │   ├── piper.py               # TTS via piper CLI
│   │   ├── vad.py                 # VAD via webrtcvad
│   │   ├── vision.py              # Vision via whisper.cpp/llama.cpp
│   │   └── dummy.py               # Dummy backends for testing
│   ├── listen.py                # Listen-only mode
│   ├── pipeline.py              # VoicePipeline: audio → audio
│   ├── preflight.py             # Deployment diagnostics
│   ├── audio.py                 # WAV helpers
│   └── errors.py                # Error classes
├── tests/
│   ├── test_*.py                # Unit tests
│   ├── conftest.py              # Pytest fixtures
│   └── support/                 # Test support modules
├── docs/
│   ├── VISION.md
│   ├── REQUIREMENTS.md
│   ├── ROADMAP.md
│   ├── ADR-001-backends-llamacpp.md
│   ├── ADR-002-subprocess-backends.md
│   ├── ADR-003-container-deployment.md
│   ├── QUALITY_GATES.md
│   ├── CHECKLIST.md
│   ├── HOSTILE_INSIGHTS.md
│   └── VOICE_INPUT.md
├── aes/
│   ├── kanban.md                # Project kanban
│   ├── tickets/                 # AES tickets
│   └── sprints/                 # Sprints
├── scripts/
│   ├── verify-implementation.sh # Acceptance criteria verification
│   └── voicevision-listen-and-copy.sh  # Listen + copy wrapper
├── docker/
│   ├── Dockerfile               # Multi-stage Docker image
│   ├── voicevision-compose.yml  # Docker Compose
│   └── entrypoint.sh            # Container entrypoint
├── .aes/
│   ├── hooks/                   # AES hooks (pre-commit, etc.)
│   └── hooks/pre-commit.sh      # Pre-commit hook
├── pyproject.toml               # Project configuration
├── Makefile                     # Build and quality gates
├── install-voice-input.sh       # System dependency installer
├── CLAUDE.md                    # AI agent operational contract
├── README.md                    # This file
└── LICENSE                      # MIT License
```

---

# 📋 Quality Gates

Run `make check` before every commit:

```bash
make check
```

This runs:

| Gate | Command |
|------|---------|
| Docs | `make docs-check` |
| Code structure | `make code-check` |
| Tests (≥80% coverage) | `make test-check` |
| Lint (ruff + mypy --strict + bandit) | `make lint-check` |

Individual targets:

```bash
make test              # unit tests (no models, no audio hardware)
make test-integration  # requires real models and audio device
make test-all          # run all tests
make test-coverage     # HTML coverage report
make lint              # ruff, mypy --strict, bandit
make format            # ruff format
make doctor            # environment status
make preflight         # why is this not working right now
```

---

# 🤝 Contributing

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

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.2.1 | 2026-11-07 | Makefile with voicevision-specific targets; docs fixes |
| 0.2.0 | 2026-11-07 | Vision backends (OpenCV + Playwright), MoondreamBackend, describe_and_answer(), conversation memory, streaming LLM → TTS |
| 0.1.1 | 2026-11-07 | Fix env-dependent tests, add vision example to README |
| 0.1.0 | 2026-11-06 | Voice loop: VAD → STT → LLM → filter → TTS; listen mode; subprocess backends; Dummy backends; preflight; quality gates |