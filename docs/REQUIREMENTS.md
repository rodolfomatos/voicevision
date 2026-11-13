# Requirements

Scope: **v0.3.x = voice loop + local HTTP server + WebSocket streaming +
MCP stdio server**. All models run as subprocesses. Ubuntu 22.04+ and
Raspberry Pi OS. Vision via Moondream GGUF + llama.cpp subprocess (ADR-001,
ADR-002).

---

## Functional Requirements — v0.3

### Pipeline

- **FR-1** The component exposes one call that runs the voice loop:
  `VoicePipeline.process(audio_bytes) -> bytes` (PCM in → synthesized speech out).
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
- **FR-6** `VoicePipeline.process()` supports `mute_tts` flag: STT → LLM →
  filter still run, but no TTS synthesis occurs.
- **FR-7** `VoicePipeline.process_stream()` yields TTS audio chunks as LLM
  generates tokens (streaming mode, sentence-by-sentence).
- **FR-8** `VoicePipeline.process_stream()` respects `mute_tts`: yields no
  TTS audio when muted.
- **FR-9** `VoicePipeline.detect_emotion(transcript)` returns emotion label
  and score (0–1) when `emotion_enabled` is True.
- **FR-10** `VoicePipeline.detect_speaker(audio, sample_rate)` returns speaker
  label (e.g. "Speaker 1") when `speaker_enabled` is True.

### Backends (subprocess-based)

- **FR-11** Every model backend runs as a **separate OS process**, communicating
  over stdin/stdout pipes. The library never links a model runtime into its
  own address space.
- **FR-12** CLI backends are one-shot: one child process per call.
  whisper.cpp and piper read input, write output, and exit; they have no
  loop mode. `communicate()` closes stdin, so a child cannot be kept alive
  between calls even in principle. The library does not pretend otherwise.
  Warm reuse applies only to the LLM daemon (FR-13), which is HTTP.
- **FR-13** Each backend exposes `available() -> bool` reporting whether its
  executable exists and is runnable, and `install_hint` naming the package
  that provides it.
- **FR-14** A child that dies mid-call is retried exactly once with a fresh
  process, then the error is surfaced. A timeout is **not** retried — it is a
  verdict about the workload, not a crash. No infinite respawn.
- **FR-15** Process stderr is captured concurrently with stdout and attached to
  any raised error, together with the command and exit code. Silent model
  failures are a bug.

### Concrete backends for v0.3

- **FR-16** `WhisperCppBackend` — drives the `whisper.cpp` CLI.
  stdin: 16 kHz mono PCM16 WAV · stdout: transcript text.
- **FR-17** `LlamaCppBackend` — supervises a `llama-server` daemon that it
  starts and keeps resident. Chosen over `llama-cli` because the server keeps
  the model loaded between calls and exposes a HTTP API. **This is the only
  warm backend.**
- **FR-18** `PiperBackend` — drives the `piper` CLI.
  stdin: text · stdout: WAV bytes.
- **FR-19** `WebrtcVadBackend` — WebRTC VAD via `webrtcvad-wheels`.
  Rationale: pure C, no torch, ~1 MB wheel, 30 ms frames.
- **FR-20** `MoondreamBackend` — describes an image via llama-server daemon
  (GGUF model, `moondream2-text-model-f16.gguf` + `moondream2-mmproj-f16.gguf`).
- **FR-21** `MoondreamBackend` (GGUF per ADR-001) — optional vision backend
  via llama-server subprocess.
- **FR-22** `MoondreamBackend` (GGUF per ADR-001) — optional vision backend
  via llama-server subprocess.
- **FR-23** `SimpleEmotionBackend` — rule-based emotion detection
  (positive/negative/neutral) using keyword matching. No external dependencies.
- **FR-24** `SimpleSpeakerBackend` — session-based speaker identification
  using audio features (RMS energy, zero-crossing rate, spectral centroid).
  Session-based: resets per pipeline session.

### Local HTTP server (T035)

- **FR-25** `voicevision-server` command exposes JSON endpoints:
  `GET /health`, `POST /transcribe`, `POST /describe`, `POST /converse`.
- **FR-26** Server binds `127.0.0.1` by default (localhost-only).
- **FR-27** Optional bearer auth via `VOICEVISION_SERVER_TOKEN`.
- **FR-28** 10 MiB body cap to prevent memory exhaustion.

### WebSocket streaming (T036)

- **FR-29** `GET /stream` accepts `audio` frames (JSON text frames,
  base64-encoded 16 kHz mono PCM16) and streams `transcript` → `token` →
  `done` messages.
- **FR-30** Supports `reset` frame to discard buffered audio.
- **FR-31** Supports ping/pong and close frames.
- **FR-32** Protocol violations (unmasked client frames, fragmented frames,
  oversized frames) close with RFC 6455 close codes.
- **FR-33** Minimal RFC 6455 codec in `voicevision.websocket` — no new
  dependency.

### Python client (T037)

- **FR-34** `VoiceVisionClient` — stdlib-only client for the local API:
  `health()`, `transcribe()`, `describe()`, `converse()`, `stream()`.
- **FR-35** Bearer token sent as `Authorization` header on both HTTP and
  WebSocket connections.
- **FR-36** All failures raise `VoiceVisionClientError` carrying the
  server's error message when available.

### Integrations (T037–T039)

- **FR-37** Home Assistant custom component: `voicevision.converse`,
  `voicevision.transcribe`, `voicevision.describe` services; fires
  `voicevision_response` event.
- **FR-38** VS Code extension: Dictate, Transcribe Audio File, Ask About
  Selection commands. Dictate shells out to `voicevision-listen`; others use
  HTTP server.
- **FR-39** Obsidian plugin (desktop-only): Transcribe audio file and Ask
  about selection commands; settings tab for server URL, token, language,
  maxTokens.
- **FR-40** Notion CLI (`voicevision_notion.py`): exports transcript (or
  locally transcribed audio) to Notion page via `POST /v1/pages`; token from
  `NOTION_TOKEN` env var; blocks split at 2000 chars.

### Streaming LLM → TTS sentence-by-sentence (T041)

- **FR-41** `VoicePipeline.process_stream()` yields TTS chunks as the LLM
  generates them, sentence-by-sentence.
- **FR-42** Sentence boundary detection: newline, space, then hard cut.
- **FR-43** Streaming respects `mute_tts` flag: no TTS chunks yielded when
  muted.
- **FR-44** Streaming respects `enable_thinking_filter`: filtered text only.

### Conversation memory persistence (T042)

- **FR-45** `VoicePipeline.process()` stores `(transcript, response)` in
  conversation history.
- **FR-46** `VoicePipeline.detect_emotion(transcript)` returns `EmotionResult`
  when `emotion_enabled` is True.
- **FR-47** `VoicePipeline.detect_speaker(audio, sample_rate)` returns speaker
  label when `speaker_enabled` is True.
- **FR-48** Conversation history persists to JSONL file when
  `conversation_enabled` is True.
- **FR-49** History file respects `max_history_size` (max turns) and
  `conversation_ttl_days` (TTTL in days).
- **FR-50** History is trimmed on save: oldest blocks removed first.
- **FR-51** `reset_context()` clears in-memory history and deletes the history
  file.

### Python client (T037)

- **FR-52** `VoiceVisionClient.health()` returns server status object.
- **FR-43** `VoiceVisionClient.transcribe()` sends base64 audio and returns
  transcript payload.
- **FR-44** `VoiceVisionClient.describe()` sends base64 image + question.
- **FR-45** `VoiceVisionClient.converse()` sends text and returns response.
- **FR-46** `VoiceVisionClient.stream()` performs WebSocket handshake, sends
  `audio`/`end` frames and yields decoded server messages.
- **FR-47** Bearer token sent as `Authorization` on both HTTP and WebSocket.
- **FR-48** All failures raise `VoiceVisionClientError` carrying the server's
  error message when available.

## Non-Functional Requirements

| ID | Category | Requirement | How verified |
|----|----------|-------------|---------------|
| NFR-1 | Performance | Bare `import voicevision` < 40 ms | `test_import_cost` asserts `pydantic` absent from `sys.modules` |
| NFR-2 | Performance | Warm LLM first-token < 500 ms on target hardware | benchmark script |
| NFR-3 | Performance | Exactly one child per STT/TTS call; one resident daemon for LLM | spawn-count assertions |
| NFR-4 | Memory | Core RSS < 50 MB; models are subprocesses | `memory_profiler` |
| NFR-5 | Testability | Every backend has `Dummy*` subclass; full loop testable with no models | `tests/test_import_cost.py` |
| NFR-6 | Testability | CI requires no model download and no audio device | CI runs `make check` only |
| NFR-7 | Portability | Zero platform-specific imports in `voicevision/core/` | grep gate in `code-check` |
| NFR-8 | Maintainability | mypy `--strict` clean; complexity ≤ 10 per function | `make lint` |
| NFR-9 | Security | Model output reaching TTS is bounded; no `shell=True` | `bandit` |
| NFR-10 | Robustness | A crashing model process cannot take down the caller | subprocess isolation test |
| NFR-11 | Security | No secrets hardcoded in source | grep gate for passwords/tokens |
| NFR-12 | Security | No cloud API calls; all inference local | review of all backend code |
| NFR-13 | Performance | `import voicevision` < 40 ms | `test_import_cost` |
| NFR-14 | Performance | Bare import < 40 ms; first `VoiceVisionConfig` access ~180 ms | measured in CI |

---

## Constraints

| Constraint | Detail |
|------------|--------|
| Language | Python 3.10+ |
| Target platform | Ubuntu 22.04+ and Raspberry Pi OS |
| Runtime deps (core) | `pydantic`, `pydantic-settings`, `typing-extensions` |
| Optional deps | declared as extras: `webrtcvad-wheels`, `sounddevice` |
| External binaries | `whisper.cpp` CLI, `llama-server`, `piper` — installed by operator |
| Model management | Paths supplied via config; `make download-models` helper |
| Network | None required at runtime. Fully offline. |
| Android | **Explicitly out of scope** — Termux/ChaQuopy audio I/O is separate |
| Cloud | **Explicitly out of scope** — all inference runs locally; Notion export |
|      | is the only cloud contact and is opt-in |

---

## Definition of Done — v0.3.0

- [ ] `pip install voicevision` on clean Ubuntu 22.04
- [ ] `make install-voice-input` installs system dependencies
- [ ] `make download-models MODELS=voice-loop` downloads all required models
- [ ] `voicevision-server` starts and answers `/health`
- [ ] `voicevision-listen --seconds 5` transcribes microphone audio
- [ ] `voicevision-server` + `voicevision-listen` work end-to-end
- [ ] Whole loop testable with `Dummy*` backends, offline, no audio hardware
- [ ] A killed model process is respawned once and failure surfaces clearly
- [ ] `make check` green; coverage ≥ 80%
- | README documents: install, model download, config, one worked example |
| ADR-001 through ADR-006 all `Accepted` |
