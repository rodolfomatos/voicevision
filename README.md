# voicevision

> Offline multimodal AI brick: VAD → STT → LLM → filter → TTS, all models as
> subprocesses. Ubuntu 22.04+ and Raspberry Pi OS. v0.1 is the voice loop;
> vision returns in v0.2 behind unchanged interfaces.

`voicevision` is a reusable Python component — a "lego brick" — for offline
multimodal AI on the edge. It is a library, not an application: the caller owns
context, models, and audio devices. Everything runs locally, with no cloud API.
An optional HTTP server binds to `127.0.0.1` only, and no model runtime is
linked into this process.

---

# 🐧 Linux Mint + OpenCode: speak instead of typing

The shortest path from a fresh Linux Mint install to dictating into OpenCode:

```bash
# 1. Clone and install (Python 3.10+; use the venv if your distro blocks pip)
git clone https://github.com/rodolfomatos/voicevision.git
cd voicevision
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Install whisper.cpp, llama.cpp, piper, xclip and the clipboard wrapper
make install-voice-input

# 3. Download the STT model (see "Download models" below for the rest)
curl -L -o /models/whisper-base.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin

# 4. Point voicevision at the model
export VOICEVISION_STT_MODEL=/models/whisper-base.bin
export VOICEVISION_STT_LANGUAGE=pt

# 5. Dictate: records, transcribes, copies to the clipboard
voicevision-listen-and-copy
```

Paste with `Ctrl+V` in OpenCode. Bind `voicevision-listen-and-copy` to a key in
**System Settings → Keyboard → Shortcuts → Custom Shortcuts** (for example
`F9`) and the whole loop becomes one keypress. See
[`docs/VOICE_INPUT.md`](docs/VOICE_INPUT.md) for the OpenCode-specific setup.

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

# piper TTS voice model (~63 MB)
curl -L -o /models/voice.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx

# piper TTS voice config (~5 KB)
curl -L -o /models/voice.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

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

# Machine-readable output for scripts and automation
voicevision-listen --seconds 5 --json

# Automation mode: only the transcript on stdout, no progress messages
voicevision-listen --seconds 5 --quiet

# Stay resident: print every wake word utterance until Ctrl+C
voicevision-listen --wake-word "Olá Ambrósio" --continuous
```

## Multiple wake words

Define multiple wake words via JSON config or env var:

```bash
# JSON file at ~/.voicevision/hotwords.json
# {"words": ["Olá Ambrósio", "Hey Ambrósio"], "threshold": 0.5}
export VOICEVISION_HOTWORDS=~/.voicevision/hotwords.json

# Or override first word via CLI
voicevision-listen --wake-word "Hey Ambrósio"
```

## Mute TTS

Run full pipeline but suppress TTS output (useful for testing/logging):

```bash
voicevision-listen --mute
# or env var
export VOICEVISION_MUTE_TTS=1
```

## Auto language detection

Let whisper.cpp detect the spoken language automatically:

```bash
voicevision-listen --language auto
# or env var
export VOICEVISION_STT_LANGUAGE=auto
```

## Emotion detection

Enable rule-based emotion classification on transcripts:

```bash
export VOICEVISION_EMOTION=1
```

Output includes `emotion: {"label": "positive|negative|neutral", "score": 0.0-1.0}`.

## Speaker identification

Enable session-based speaker tracking:

```bash
export VOICEVISION_SPEAKER=1
```

Output includes `speaker: "Speaker 1|2|..."` per utterance.

## AES Skills

The project includes several AES skills for development workflow:

| Skill | Command | Purpose |
|-------|---------|---------|
| `aes-preflight` | `make aes-preflight` | Pre-flight diagnostics (skills, hooks, config) |
| `aes-conflict` | `make aes-conflict` | Cross-session conflict detection |
| `aes-epistemics` | `make gmif-check` | GMIF v2 SAT validation of island graphs |
| `aes-wake` | `make aes-wake` | Load relevant context before phases |
| `aes-sleep` | `make aes-sleep` | Archive stale docs, regenerate index |

Run `make check` to execute all quality gates including these skills.

## With clipboard (for OpenCode / any editor)

```bash
voicevision-listen-and-copy
```

This records 5 seconds, transcribes, and copies the result to your clipboard.
Then paste with `Ctrl+V` into any application.

## Transcript history

Every successful transcription is appended as one JSON object per line to
`~/.voicevision/history.jsonl` (created with `0600` permissions inside a
`0700` directory). Disable it with `--no-history` or
`VOICEVISION_HISTORY_ENABLED=0`.

```bash
# Show the 10 most recent transcripts
voicevision-history --limit 10

# Raw JSON Lines (for scripts)
voicevision-history --json

# Empty the file
voicevision-history --clear
```

## Keybind setup (Cinnamon desktop)

System Settings → Keyboard → Shortcuts → Custom Shortcuts → +

| Field | Value |
|-------|-------|
| Name | Voice → Text |
| Command | `~/.local/bin/voicevision-listen-and-copy` |
| Shortcut | `F9` (or your choice) |

See `docs/VOICE_INPUT.md` for full documentation.

---

# 🌐 Local HTTP server

Editor plugins, Home Assistant and other processes can call voicevision over a
small localhost HTTP API instead of importing Python internals.

```bash
# Start on 127.0.0.1:8765 (default)
voicevision-server

# Different port, bearer auth required
VOICEVISION_SERVER_TOKEN=change-me voicevision-server --port 9000

# Only use --host when you really mean to expose it
voicevision-server --host 0.0.0.0 --token change-me
```

| Endpoint | Request | Response |
|----------|---------|----------|
| `GET /health` | — | `{"status": "ok", "version": "0.1.0"}` |
| `POST /transcribe` | `{"audio_base64": "...", "language": "pt"}` | `{"transcript", "language", "transcription_ms"}` |
| `POST /describe` | `{"image_base64": "...", "question": "What is this?"}` | `{"description"}` |
| `POST /converse` | `{"text": "...", "max_tokens": 128}` | `{"response"}` |
| `GET /stream` | WebSocket upgrade | Streaming JSON messages |

Audio may be raw 16 kHz mono PCM16 or a WAV file. Errors are JSON
(`{"error": "..."}`) with 400 for bad requests, 401 for a missing/wrong bearer
token, 404/405 for routing mistakes, 413 above 10 MiB, and 502 when a backend
fails.

## WebSocket streaming

`/stream` avoids buffering a whole utterance in the client. Send masked text
frames containing JSON, and read JSON frames back:

```jsonc
// client → server
{"type": "audio", "audio_base64": "...", "language": "pt"}
{"type": "audio", "audio_base64": "..."}
{"type": "end"}

// server → client
{"type": "transcript", "transcript": "...", "language": "pt", "transcription_ms": 42.1}
{"type": "token", "text": "Hello"}
{"type": "token", "text": " world"}
{"type": "done"}
```

`{"type": "reset"}` discards buffered audio. Malformed JSON and backend
failures return `{"type": "error", "error": "..."}` without dropping the
socket; protocol violations close it with the RFC 6455 code (1002 unmasked,
1003 fragmented/binary, 1007 invalid UTF-8, 1009 oversized frame). The codec
is implemented with the standard library — no extra dependency.

## Python client

`voicevision.client` wraps the same API for Python callers (standard library
only):

```python
from voicevision.client import VoiceVisionClient

client = VoiceVisionClient("http://127.0.0.1:8765")
print(client.health())

print(client.transcribe(audio_bytes, language="pt")["transcript"])
print(client.converse("Explain VAD in one sentence.")["response"])

for message in client.stream([chunk1, chunk2], language="pt"):
    if message["type"] == "token":
        print(message["text"], end="", flush=True)
```

Every failure raises `VoiceVisionClientError` carrying the server's own error
message.

## Integrations

Ready-to-use clients live in [`integrations/`](integrations/):

| Integration | Path | Talks to |
|-------------|------|----------|
| Home Assistant | `integrations/homeassistant/` | HTTP via `voicevision.client` |
| VS Code | `integrations/vscode/` | HTTP `/transcribe` |
| Obsidian | `integrations/obsidian/` | HTTP `/transcribe`, `/converse` |
| Notion | `integrations/notion/` | HTTP via `voicevision.client` |

Each directory has its own README with installation and usage instructions.


## MCP Server (stdio)

`voicevision-mcp` expõe as capacidades do voicevision como ferramentas MCP (Model Context
Protocol), permitindo que agentes de IA usem o voicevision como ferramenta
através de JSON-RPC over stdio:

```bash
voicevision-mcp
```

Ferramentas expostas:

| Ferramenta | Descrição |
|-----------|-----------|
| `transcribe_audio` | Transcreve áudio em base64 (WAV, 16 kHz mono PCM16) para texto |
| `describe_image` | Descreve imagem ou responde pergunta sobre ela |
| `converse_text` | Envia texto para o LLM |
| `health_check` | Verifica status do servidor voicevision |

Exemplo de chamada MCP:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "transcribe_audio",
    "arguments": {
      "audio_base64": "<base64-encoded-wav>",
      "language": "pt"
    }
  }
}
```

Resposta:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"transcript\": \"Olá, como vai você?\", \"language\": \"pt\", \"transcription_ms\": 850.2}"
      }
    ]
  }
}
```

O servidor MCP roda via stdio e é ideal para integração com clientes MCP (Claude, OpenCode, etc.) que suportam o protocolo MCP.

---


```bash
# Example: transcribe a WAV file
base64 -w0 speech.wav > /tmp/audio.b64
curl -s http://127.0.0.1:8765/transcribe \
  -H 'Content-Type: application/json' \
  -d "{\"audio_base64\": \"$(cat /tmp/audio.b64)\", \"language\": \"pt\"}"
```

---

# 📖 Documentação completa

O `docs/USAGE.md` contém um guia completo com exemplos práticos de uso da
biblioteca voicevision, incluindo:

- Instalação passo a passo
- Listen mode (ditando para qualquer editor)
- Servidor HTTP local e cliente Python
- Pipeline completo com `VoicePipeline`
- Todas as integrações (Home Assistant, VS Code, Obsidian, Notion)
- Solução de problemas comuns

Leia antes de começar a usar o projeto em produção.

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
│   ├── server.py                # Local HTTP API (/health, /transcribe, …)
│   ├── client.py                # Stdlib client for the local API
│   ├── websocket.py             # Minimal RFC 6455 codec for /stream
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

### Benchmarking

Measure performance across backends:

```bash
# Run all benchmarks (voice-loop models)
make benchmark MODELS=voice-loop

# Run specific backend groups
make benchmark MODELS=stt
make benchmark MODELS=llm
make benchmark MODELS=tts

# Output results
make benchmark MODELS=voice-loop --output benchmark.json --output-csv benchmark.csv
```

Measures TTFT (Time To First Token), RTF (Real Time Factor), and RSS (memory).

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
| Unreleased | 2026-11-13 | Piper TTS fix, custom hotwords, mute TTS, multiple wake words, auto language detection, emotion detection, speaker ID, sentence-by-sentence streaming LLM→TTS, conversation memory persistence, model download helper (make download-models), benchmark suite (make benchmark), aes-conflict skill, aes-preflight, aes-epistemics |
| 0.2.2 | 2026-11-09 | Vision backends (OpenCV + Playwright), MoondreamBackend, describe_and_answer(), conversation memory, streaming LLM → TTS |
| 0.2.1 | 2026-11-07 | Makefile with voicevision-specific targets; docs fixes |
| 0.2.0 | 2026-11-07 | Vision backends (OpenCV + Playwright), MoondreamBackend, describe_and_answer(), conversation memory, streaming LLM → TTS |
| 0.1.1 | 2026-11-07 | Fix env-dependent tests, add vision example to README |
| 0.1.0 | 2026-11-06 | Voice loop: VAD → STT → LLM → filter → TTS; listen mode; subprocess backends; Dummy backends; preflight; quality gates |