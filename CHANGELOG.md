# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`voicevision-listen --json`** (T025): structured output with `transcript`,
  ISO 8601 `timestamp`, `language`, `audio_duration_seconds`,
  `transcription_ms`, and `wake_word_detected` / `wake_word` in wake word mode
- **`voicevision-listen --quiet`** (T026): suppresses progress and outcome
  messages on stderr, leaving only the transcript (or JSON) on stdout. Fatal
  errors are still reported. Also configurable via `VOICEVISION_QUIET=1`
- **Transcript history** (T027): every transcription is appended to
  `~/.voicevision/history.jsonl` (JSON Lines, `0600`). New `voicevision-history`
  CLI lists or clears it; `--no-history` and `VOICEVISION_HISTORY_ENABLED=0`
  opt out
- **Continuous wake word mode** (T030): `--continuous` keeps listening and
  prints every wake word utterance until `Ctrl+C`; each detection is recorded
  in the history with its wake word

### Fixed

- Single-shot wake word mode no longer raises `AssertionError` when it hears
  speech that does not contain the wake word (`_transcribe_utterances` now
  returns `None` instead of a `(None, None)` tuple)
- `tests/backends/test_vad.py` and `tests/test_vision.py` no longer depend on
  optional packages being installed or absent in the running environment
- `make code-check` no longer scans generated `*.egg-info` directories when
  looking for `TODO:` / `FIXME:` markers
- mypy no longer fails on missing stubs for optional dependencies
  (`webrtcvad`, `httpx`, `playwright`)

### Documentation

- `README.md` and `docs/VOICE_INPUT.md` document `--json`, `--quiet`, and
  `VOICEVISION_QUIET`

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
