# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Piper TTS fix** — valid Piper voice model (`en_US-lessac-medium`) and config downloaded via `huggingface_hub`; replaced corrupted `voice.onnx` (14 bytes) and `voice.onnx.json` (1.5 KB) with valid files
- **Custom hotword file** (T028): `VOICEVISION_HOTWORDS` env var points to JSON file with multiple wake words; `--hotwords-file` CLI; backward compatible with `VOICEVISION_WAKE_WORD`
- **Mute TTS flag** (T029): `--mute` / `VOICEVISION_MUTE_TTS` skips TTS synthesis while running full pipeline
- **Multiple wake words** (T031): `VOICEVISION_HOTWORDS` JSON supports multiple wake words; any match triggers; matched word returned for logging/history
- **Auto language detection** (T032): `voicevision-listen --language auto` / `VOICEVISION_STT_LANGUAGE=auto` uses whisper.cpp `--detect-language`; HTTP `/transcribe` returns `detected_language`
- **Emotion detection** (T033): `VOICEVISION_EMOTION=1` enables rule-based sentiment (positive/negative/neutral) on transcripts via `SimpleEmotionBackend`
- **Speaker identification** (T034): `VOICEVISION_SPEAKER=1` enables session-based speaker tracking via RMS/ZCR/spectral centroid features; returns `Speaker 1`, `Speaker 2`, etc.
- **aes-conflict skill** (T040): `make aes-conflict` detects 5 conflict types (orphan refs, epistemic contradictions, causality violations, session conflicts, stale refs) via Z3 SAT solving
- **aes-preflight integration**: `make aes-preflight` now part of `make check`; validates skills, hooks, config, recent commits
- **aes-epistemics integration**: `make gmif-check` + `gmif-staleness` in quality gates; Z3 SAT validation of island graphs; self-ticket on UNSAT
- **Piper TTS model download** updated to `en_US-lessac-medium` via `huggingface_hub` (was broken `kokoro` model)
- **Local HTTP server** (T035): new `voicevision-server` command exposing `GET /health`, `POST /transcribe`, `POST /describe` and `POST /converse` as JSON. Standard library only, binds `127.0.0.1` by default, optional bearer auth via `VOICEVISION_SERVER_TOKEN`, 10 MiB body cap
- **WebSocket streaming** (T036): `GET /stream` accepts `audio` frames and streams `transcript` → `token` → `done`, plus `reset`, ping/pong and close. Minimal RFC 6455 codec in `voicevision.websocket` with no new dependency; unmasked/fragmented/oversized frames close with the RFC code
- **Python client and Home Assistant integration** (T037): `voicevision.client` is a standard-library client for the local API, including WebSocket streaming. `integrations/homeassistant/` adds `voicevision.converse`, `voicevision.transcribe` and `voicevision.describe` services that fire a `voicevision_response` event
- **VS Code extension** (T038): `integrations/vscode/` adds Dictate, Transcribe Audio File and Ask About Selection commands. Plain JavaScript, no build step; dictation shells out to `voicevision-listen`, the other two use the local HTTP server
- **MCP server** (T045): `src/voicevision/backends/mcp_server.py` — stdio MCP server exposing `transcribe_audio`, `describe_image`, `converse_text`, `health_check` tools; `Makefile` target `make aes-mcp-server`; `pyproject.toml` console script `voicevision-mcp`
- **ONNX Runtime vision backend** (T044/B6): `src/voicevision/backends/onnx_vision.py`
  adds `OnnxVisionBackend` for ONNX Runtime vision inference, sharing the ONNX
  Runtime dependency with Piper TTS. `PipelineConfig.vision_backend` selects
  `onnx` or `llama-cpp` (default). Tests with mocked ONNX Runtime.
- - **Obsidian plugin and Notion export** (T039): `integrations/obsidian/` adds Transcribe audio file and Ask about selection commands plus a settings tab; `integrations/notion/` exports a transcript (or locally transcribed audio) to a Notion page. Notion export is the only opt-in cloud step — inference stays local and the token comes from `NOTION_TOKEN`
- **Sentence-by-sentence streaming LLM → TTS** (T041/B1): `_stream_transcript` now splits LLM response into sentences using proper boundary detection; only sends newly synthesized sentences to TTS; handles abbreviations, ellipsis, quotes, parentheses
- **Conversation memory persistence** (T042/B2): `PipelineConfig` gains `conversation_path`, `conversation_ttl_days`, `max_history_size`; `VoicePipeline.load_context()` / `save_context()` with thread-safe locking; JSONL format; TTL expiry on load; size limit on save; auto-save on close/`__exit__`
- **Model download helper** (`make download-models`): `scripts/download_models.py` downloads all models via `huggingface_hub`; supports model groups (`stt`, `llm`, `tts`, `vision`, `voice-loop`, `full`, `all`) and individual models; skips existing files
- **Benchmark suite** (T043/B3): `scripts/benchmark.py` measures TTFT (STT + LLM), RTF (TTS), RSS; `make benchmark MODELS=...` target; outputs JSON/CSV; supports iterations, warmup, dry-run
- **MCP server** (T044): `src/voicevision/backends/mcp_server.py` — stdio MCP server exposing `transcribe_audio`, `describe_image`, `converse_text`, `health_check` tools; `Makefile` `make mcp-server` target; `pyproject.toml` console script

### Fixed

- Single-shot wake word mode no longer raises `AssertionError` when it hears speech that does not contain the wake word (`_transcribe_utterances` now returns `None` instead of a `(None, None)` tuple)
- `tests/backends/test_vad.py` and `tests/test_vision.py` no longer depend on optional packages being installed or absent in the running environment
- `make code-check` no longer scans generated `*.egg-info` directories when looking for `TODO:` / `FIXME:` markers
- mypy no longer fails on missing stubs for optional dependencies (`webrtcvad`, `httpx`, `playwright`)
- Piper TTS: replaced corrupted model files with valid `en_US-lessac-medium` via `huggingface_hub`
- Island graph epistemic contradictions resolved (C-200, C-206, C-403 states corrected; edge C-403→C-206 changed from `factual` to `not`)

### Documentation

- `README.md` updated: Piper model URLs fixed, new feature sections added (custom hotwords, mute TTS, auto language, emotion, speaker ID, AES skills)
- `README.md` version history updated with v0.2.2
- `README.md` updated: version history updated with v0.3.0
- `docs/USAGE.md` added: complete usage guide with listen mode, HTTP server, Python client, integrations, and troubleshooting
- `README.md` updated: quick reference to `docs/USAGE.md`
- `CHANGELOG.md` consolidated all recent changes
- `CLAUDE.md` non-goals updated: optional HTTP server is localhost-only by default, history is opt-in rather than forbidden
- `docs/VOICE_INPUT.md` documents `--json`, `--quiet`, `VOICEVISION_QUIET`, and the local HTTP server

## [0.2.2] - 2026-11-07

### Documentation

- Complete `README.md`: quick start (install, model download, env config),
  worked example, voice input, vision, project structure, quality gates,
  contributing guidelines, version history

## [0.2.1] - 2026-11-07

### Added

- Comprehensive `Makefile` with voicevision-specific targets:
  `install-voice-input`, `install-deps`, `setup-env`, `run-listen`,
  `run-listen-wake`, `doctor-full`

## [0.2.0] - 2026-11-07

### Added

- **Vision backends**: OpenCV (local webcam) + Playwright (web page screenshots)
- **Vision backend**: Moondream GGUF via llama.cpp subprocess (`MoondreamBackend`)
- **Describe & Answer pipeline**: `VoicePipeline.describe_and_answer(image_data, question)` — captures image, transcribes via vision model, generates LLM response, synthesizes TTS
- **Conversation memory**: `VoicePipeline` stores conversation history and prepends it to LLM prompts (`max_context_utterances` config, default: 5)
- **Streaming LLM → TTS**: `streaming_enabled` config option; `process_stream()` sends TTS chunks as LLM generates them, reducing perceived latency
- **VoicePipeline.reset_context()**: clears conversation history

### Configuration

- New env vars: `VOICEVISION_VISION_BACKEND`, `VOICEVISION_VISION_MODEL`, `VOICEVISION_STREAMING_ENABLED`

## [0.1.1] - 2026-11-07

### Fixed

- `test_whisper_cpp.py::TestConstruction::test_available_is_false_without_binary` — now mocks `shutil.which` instead of relying on whisper.cpp being absent
- `test_preflight.py::TestExecutableChecks::test_missing_binary_names_the_fix` — now mocks `shutil.which` instead of relying on backends being absent

### Added

- Example of `describe_and_answer()` with a real image in `README.md`
- Vision (v0.2) section in `README.md` with camera backends and setup instructions

## [0.1.0] - 2026-11-07

### Added

- **Voice loop**: VAD → STT → LLM → filter → TTS pipeline (end-to-end voice in, audio out)
- **Listen mode**: microphone → STT → text on stdout (`voicevision-listen` CLI)
- **Wake word**: configurable wake word detection (default: "Olá Ambrósio") with VAD adaptive triggering
- **Pre-roll circular buffer**: captures audio before wake word detection so no speech is lost
- **Multiple STT models**: whisper-base, whisper-small, whisper-tiny, whisper-medium, whisper-large
- **Camera backends**: OpenCV (local webcam) + Playwright (web page screenshots)
- **Vision backend**: Moondream GGUF via llama.cpp subprocess
- **Describe & Answer**: image → text transcription → LLM response → TTS synthesis pipeline
- **Preflight utility**: `voicevision-preflight` CLI for deployment diagnostics
- **Docker deployment**: multi-stage image, docker-compose, ADR-003 compliance (tini PID 1, /dev/snd passthrough, models as volume)

### Backends

| Modality | Backend | Runtime |
|----------|---------|---------|
| LLM | LlamaCppBackend | llama.cpp / GGUF / llama-server |
| STT | WhisperCppBackend | whisper.cpp CLI |
| TTS | PiperBackend | piper CLI |
| VAD | WebrtcVadBackend | webrtcvad-wheels |
| Vision | MoondreamBackend | llama.cpp / GGUF |
| Camera | OpenCvCameraBackend | OpenCV (webcam) |
| Camera | PlaywrightCameraBackend | Playwright (web page) |

All backends are `dummy`-backed by default for testing without hardware/models.

### Configuration

- `VoiceVisionConfig` with `VOICEVISION_*` env prefix
- All backends configurable via environment variables
- Lazy imports: heavy dependencies (torch, torchvision, cv2, sounddevice) loaded only when needed
- No model runtime linked into this process (ADR-001, ADR-002)

### Quality Gates

- ruff linting, mypy --strict, bandit security scanning
- pytest with ≥80% test coverage
- `make check`, `make test`, `make lint`, `make format` targets
- Pre-commit hook via `.aes/hooks/pre-commit.sh`

### Documentation

- `docs/VISION.md` — problem, solution, value proposition
- `docs/REQUIREMENTS.md` — functional + non-functional requirements (FR-1..FR-20, NFR-1..NFR-10)
- `docs/ROADMAP.md` — sprints, backlog, Definition of Done
- `docs/ADR-001-backends-llamacpp.md` — llama.cpp / GGUF single runtime decision
- `docs/ADR-002-subprocess-backends.md` — subprocess backend decision
- `docs/ADR-003-container-deployment.md` — containerized deployment decision
- `docs/QUALITY_GATES.md` — quality gate configuration
- `docs/CHECKLIST.md` — pre-commit / pre-release checklist
- `docs/HOSTILE_INSIGHTS.md` — lessons from hostile analysis
- `docs/VOICE_INPUT.md` — dictation hotkey setup (editor integration)
- `README.md` — installation, model acquisition, configuration, worked example
