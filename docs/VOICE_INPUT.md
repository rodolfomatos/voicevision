# Voice Input — Dictation for OpenCode

This document describes how to set up a global hotkey to speak into a
microphone and have the transcribed text available to paste into the OpenCode
chat input, using the `listen` mode of voicevision.

It is written for developers and operators who want to integrate voice dictation
into their OpenCode workflow on Linux (X11/Cinnamon). Every step, prerequisite,
configuration variable, and failure mode is documented.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Installation (one command)](#installation-one-command)
5. [Configuration](#configuration)
6. [Environment Variables](#environment-variables)
7. [Usage](#usage)
8. [Cinnamon Global Hotkey Setup](#cinnamon-global-hotkey-setup)
9. [Troubleshooting](#troubleshooting)
10. [Files in the Project](#files-in-the-project)
11. [Known Limitations](#known-limitations)
12. [Security Considerations](#security-considerations)
13. [License](#license)

---

## Overview

OpenCode does not allow keybinds that execute arbitrary shell commands
(keybinds in `tui.json` are limited to predefined actions: navigation,
input editing, paste from clipboard). Therefore, voice dictation requires a
**global desktop hotkey** that:

1. Runs `voicevision-listen` (microphone → WebRTC VAD → whisper.cpp STT → text on stdout)
2. Copies the text to the clipboard (`xclip`)
3. In OpenCode, you focus the input and paste with `ctrl+v`

Audio never leaves the local machine — this respects the voicevision
non-goal of network serving (no HTTP/gRPC surface).

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Microphone     │─────▶│  voicevision     │─────▶│  whisper.cpp    │
│  (VAD capture)  │      │  listen mode     │      │  (STT backend)  │
└─────────────────┘      └──────────────────┘      └─────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │  text on stdout │
                                              └─────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │  xclip          │─────▶ clipboard
                                              └─────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │  OpenCode input │◄── ctrl+v
                                              └─────────────────┘
```

### Components

| Component | Responsibility |
|-----------|----------------|
| `voicevision-listen` (CLI) | Captures microphone audio, segments with WebRTC VAD, transcribes via whisper.cpp, prints transcript to stdout |
| `WebrtcVadBackend` | Voice activity detection — segments PCM16 audio into utterances based on speech/silence frames |
| `WhisperCppBackend` | One-shot whisper.cpp CLI invocation — reads WAV from stdin, prints transcript to stdout |
| `pcm16_to_wav` | Wraps raw PCM16 in a WAV container (16 kHz, mono, 16-bit) |
| `voicevision-listen-and-copy` (shell wrapper) | Orchestrates the above: sets PATH, loads `~/.bashrc`, runs `voicevision-listen`, copies result to clipboard via `xclip`, sends desktop notification |
| `xclip` | X11 clipboard utility |
| Cinnamon global hotkey | Desktop shortcut that executes the wrapper script |

### Audio Format Contract

whisper.cpp requires **16 kHz mono PCM16 WAV**. The capture layer (`sounddevice`)
produces PCM16 at 16 kHz mono, which `pcm16_to_wav` wraps in a WAV header.
`require_whisper_format` validates this strictly — no silent resampling.

### VAD Behavior (default mode)

By default (no `--seconds` flag), `voicevision-listen` uses **Voice Activity Detection**:

- Captures microphone audio continuously
- Segments with WebRTC VAD (aggressiveness level 0-3, default 2)
- When speech is detected, transcribes the utterance via whisper.cpp
- Stops recording after `VOICEVISION_VAD_SILENCE_MS` of consecutive silence (default: 2000 ms = 2 seconds)
- Maximum recording duration is `VOICEVISION_MAX_RECORD_SECONDS` (default: 60 seconds)

This means: you press the hotkey, speak, pause for ~2 seconds, and the
transcription appears automatically. No fixed time limit.

### Fixed-Duration Mode (optional)

Use `--seconds N` to record for exactly N seconds regardless of VAD:

```bash
voicevision-listen --seconds 5
```

Useful when VAD is unreliable (very quiet voice, heavy background noise).

---

## Prerequisites

### Hardware

- A working microphone connected to the machine where OpenCode runs
- Audio device accessible (on Linux: `/dev/snd` present; in containers:
  pass `--device /dev/snd`)

### System Packages

| Package | Purpose |
|---------|---------|
| `xclip` | X11 clipboard utility |
| `cmake` | Build whisper.cpp |
| `build-essential` | Compiler toolchain for whisper.cpp |
| `git` | Clone whisper.cpp source |
| `curl` | Download STT model |
| `python3-pip` | Install Python package |

### Python Package

The `voicevision` package (installed from this repo) provides:
- `voicevision-listen` CLI entry point
- `WebrtcVadBackend`, `WhisperCppBackend`, `pcm16_to_wav`
- Python extra `audio` → `sounddevice>=0.4.6` (microphone capture)

### STT Model

whisper.cpp requires a model file (GGML format `.bin`). The installer downloads
`whisper-base.bin` (multilingual, ~142 MB) which supports Portuguese and many
other languages.

Alternative models can be used by setting `VOICEVISION_STT_MODEL` to a
different `.bin` path.

---

## Installation (one command)

Run as a user with `sudo` privileges:

```bash
make install-voice-input
```

This executes `install-voice-input.sh` and performs, automatically:

| Step | Action |
|------|--------|
| 1 | Install system dependencies: `xclip`, `cmake`, `build-essential`, `git`, `curl`, `python3-pip` |
| 2 | Clone whisper.cpp, build `whisper-cli` with shared libraries (`-DBUILD_SHARED_LIBS=ON`), install binary to `/usr/local/bin/whisper-cli` |
| 3 | Install all shared libraries (`libwhisper.so.1`, `libggml.so.0`, etc.) to `/usr/local/lib/` and run `ldconfig` |
| 4 | Download `whisper-base.bin` STT model to `/models/` |
| 5 | Install the `voicevision` Python package (`pip install -e . --break-system-packages --ignore-installed`) |
| 6 | Install `sounddevice` Python package (microphone capture) |
| 7 | Install `~/.local/bin/voicevision-listen-and-copy` wrapper script |
| 8 | Add `VOICEVISION_STT_MODEL`, `VOICEVISION_STT_LANGUAGE`, and VAD variables to `~/.bashrc` |

No manual steps are required after this command completes.

### Manual Installation (if `make` is not available)

```bash
sudo sh install-voice-input.sh
source ~/.bashrc
```

---

## Configuration

### Environment Variables

All variables are read from `~/.bashrc` (loaded by the wrapper) and can be
overridden per-invocation. Prefix: `VOICEVISION_`.

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICEVISION_STT_MODEL` | `/models/whisper-base.bin` | Path to whisper.cpp model file (`.bin`) |
| `VOICEVISION_STT_LANGUAGE` | `pt` | STT language code (e.g. `pt`, `en`) |
| `VOICEVISION_VAD_AGGRESSIVENESS` | `2` | WebRTC VAD aggressiveness (0-3, higher = more aggressive speech detection) |
| `VOICEVISION_VAD_SILENCE_MS` | `2000` | Milliseconds of silence to end an utterance (default: 2000 = 2 seconds) |
| `VOICEVISION_VAD_MAX_UTTERANCE_MS` | `30000` | Maximum utterance length in ms (runaway protection) |
| `VOICEVISION_MAX_RECORD_SECONDS` | `60` | Maximum total recording time in seconds |

### Example: English language, 3-second silence threshold

Add to `~/.bashrc`:

```bash
export VOICEVISION_STT_MODEL="/models/whisper-base.bin"
export VOICEVISION_STT_LANGUAGE="en"
export VOICEVISION_VAD_SILENCE_MS="3000"
```

Then `source ~/.bashrc`.

### Example: Custom model path

```bash
export VOICEVISION_STT_MODEL="/models/ggml-amalia.bin"
```

The model file must be in whisper.cpp GGML format (`.bin`). Safetensors/PyTorch
models (e.g. from Hugging Face `transformers`) are **not** compatible with
whisper-cli and must be converted first.

---

## Usage

### Via Global Hotkey (recommended)

1. Focus the OpenCode chat input field
2. Press your configured hotkey (e.g. `F9`)
3. Speak clearly
4. Pause for ~2 seconds (or until recording stops automatically)
5. A desktop notification shows the transcribed text
6. The text is in your clipboard
7. In OpenCode, press `ctrl+v` to paste
8. Review the text (the agent will act on it)
9. Press `Enter` to send

### Via Command Line (testing)

```bash
source ~/.bashrc
voicevision-listen --seconds 5
# speak for 5 seconds
# transcript printed to stdout

xclip -selection clipboard -o
# verify clipboard content
```

### Via CLI with VAD (default, adaptive)

```bash
source ~/.bashrc
voicevision-listen
# speaks until 2 seconds of silence, then transcribes
```

### CLI Options

| Option | Description |
|--------|-------------|
| `--model PATH` | Override `VOICEVISION_STT_MODEL` |
| `--language CODE` | Override `VOICEVISION_STT_LANGUAGE` (default: `en`) |
| `--seconds N` | Record for fixed N seconds instead of VAD detection |

---

## Cinnamon Global Hotkey Setup

OpenCode keybinds (`tui.json`) cannot execute arbitrary shell commands, so a
desktop-level hotkey is required.

### Steps (Cinnamon desktop)

1. Open **Menu → Preferences → Keyboard → Shortcuts** (or "Keyboard → Shortcuts")
2. Go to the **Custom Shortcuts** section
3. Click **"+" / Add custom shortcut**
4. Fill in:
   - **Name:** `Voice → Text (OpenCode)`
   - **Command:** `/home/rodolfo/.local/bin/voicevision-listen-and-copy`
   - **Shortcut:** Choose a key that doesn't conflict (e.g. `F9`, `ctrl+alt+v`, `super+v`)
5. Save

### How the wrapper works in a global shortcut context

Global desktop shortcuts run in a limited environment: they do **not** load
`~/.bashrc`, have a restricted `PATH`, and may lack `DISPLAY`. The wrapper
script handles all of this:

- Sets `HOME` explicitly
- Ensures `PATH` includes `$HOME/.local/bin`, `/usr/local/bin`, `/usr/bin`, `/bin`
- Loads `~/.bashrc` to get `VOICEVISION_STT_MODEL` and other variables
- Falls back to sensible defaults if variables are missing
- Exports `DISPLAY=:0` for desktop notifications

---

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Shortcut does nothing | `~/.bashrc` not loaded in shortcut context | The wrapper now loads it; ensure `VOICEVISION_STT_MODEL` is in `~/.bashrc` |
| `whisper-cli: error while loading shared libraries` | `libwhisper.so.1` or `libggml.so.0` not in linker path | Re-run `make install-voice-input` (installs all `.so` to `/usr/local/lib/` + `ldconfig`) |
| `sounddevice` ImportError | PortAudio not installed | `sudo apt-get install libportaudio2`; reinstall `sounddevice` Python package |
| `ModuleNotFoundError: No module named 'voicevision'` | Package not installed | `cd /opt/voicevision && pip3 install --break-system-packages --ignore-installed -e .` |
| "No speech detected" | Microphone not capturing, or VAD too sensitive | Check `arecord -l`; adjust `VOICEVISION_VAD_AGGRESSIVENESS` (0-3) or `VOICEVISION_VAD_SILENCE_MS` |
| Transcription is empty/wrong | Wrong language, or model mismatch | Set `VOICEVISION_STT_LANGUAGE` correctly; verify model file exists |
| `xclip` not found | Clipboard utility missing | `sudo apt-get install xclip` |
| No desktop notification | `notify-send` missing or `DISPLAY` not set | Install `libnotify-bin`; ensure `DISPLAY=:0` |

### Test the Pipeline Step by Step

1. **Verify whisper-cli:**
   ```bash
   whisper-cli -h
   ```

2. **Verify model exists:**
   ```bash
   ls -lh /models/whisper-base.bin
   ```

3. **Test STT with a synthetic WAV:**
   ```bash
   python3 -c "
   import wave, math
   frames = 16000 * 3
   with wave.open('/tmp/test.wav', 'wb') as w:
       w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
       for i in range(frames):
           val = int(16000 * math.sin(2 * math.pi * 440 * i / 16000))
           w.writeframes(val.to_bytes(2, 'little', signed=True))
   "
   whisper-cli -m /models/whisper-base.bin -f /tmp/test.wav -l pt -otxt -of - -nt -np
   ```

4. **Test full pipeline:**
   ```bash
   source ~/.bashrc
   voicevision-listen --seconds 5
   ```

---

## Files in the Project

| File | Purpose |
|------|---------|
| `src/voicevision/listen.py` | Listen mode: microphone → VAD → STT → stdout. Contains `ListenConfig`, `load_config()`, `_capture_until_utterance()`, `_capture_fixed_seconds()`, `_transcribe_pcm()`, `run()`, `main()` |
| `tests/test_listen.py` | 20 unit tests (env parsing, config loading, capture with fake sounddevice/VAD, fixed-duration capture, transcription with fake child, run orchestration). 1 integration test (skipped by default) |
| `pyproject.toml` | Entry point: `voicevision-listen = "voicevision.listen:main"` |
| `Makefile` | Target `install-voice-input` |
| `install-voice-input.sh` | Complete installation script (requires sudo): system deps, whisper.cpp build, model download, Python package, wrapper, env vars |
| `scripts/voicevision-listen-and-copy.sh` | Wrapper: sets PATH, loads `~/.bashrc`, runs `voicevision-listen`, copies to clipboard via `xclip`, sends notification |
| `docs/VOICE_INPUT.md` | This document |
| `aes/tickets/T013-listen-mode.md` | AES ticket for this work |
| `aes/kanban.md` | AES kanban board |

---

## Known Limitations

| Item | Detail |
|------|--------|
| Latency | whisper.cpp takes seconds per utterance — not real-time fluent conversation |
| No direct input injection | Text goes to clipboard, not injected into OpenCode input (OpenCode limitation) |
| Microphone absent | If OpenCode runs in a container without `/dev/snd`, capture fails with a clear error |
| STT model | `whisper-base.bin` downloaded automatically; other models must be GGML `.bin` format |
| xclip | Required on X11; on Wayland use `wl-copy` instead |
| VAD sensitivity | WebRTC VAD may miss quiet voices or detect background noise as speech. Adjust `VOICEVISION_VAD_AGGRESSIVENESS` / `VOICEVISION_VAD_SILENCE_MS` |
| Global shortcut environment | Cinnamon shortcuts don't load `~/.bashrc`; the wrapper compensates but may need tuning on other desktop environments |
| Model format | Safetensors/PyTorch models (e.g. Hugging Face `amalia-llm/CAMOES-whisper-asr`) are **not** compatible with whisper-cli. They must be converted to GGML `.bin` format first |

---

## Security Considerations

- **Audio stays local:** No audio or transcript is sent over the network. whisper.cpp runs as a local subprocess (per ADR-002 in voicevision).
- **Clipboard:** The transcribed text is placed in the X11 clipboard. Any application with clipboard access can read it.
- **Desktop notifications:** The transcript appears in a notification. Avoid dictating sensitive information if others can see your screen.
- **Model files:** The STT model is downloaded from Hugging Face (`ggerganov/whisper.cpp`) and stored in `/models/`. Verify the source if operating in high-security environments.
- **No secrets:** Never put API keys, passwords, or tokens in `VOICEVISION_*` environment variables.

---

## License

This feature is part of the voicevision project, licensed under MIT. See `LICENSE` in the project root.

The whisper.cpp model (`whisper-base.bin`) is distributed under its own license (see the whisper.cpp repository for details).

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-11-06 | Initial voice input documentation: installation, configuration, usage, Cinnamon hotkey setup, troubleshooting, security considerations |
