# voicevision for Obsidian

Transcribe an audio file or ask the local LLM about the selected text, directly
in a note. All inference runs on the local `voicevision-server`; nothing is sent
to a cloud service.

## Requirements

- Obsidian 1.4+ on desktop (the plugin reads files with Node's `fs`)
- `voicevision-server` running and configured with the models you need:

  ```bash
  export VOICEVISION_STT_MODEL=/models/whisper-base.bin
  export VOICEVISION_LLM_MODEL=/models/Qwen3-1.7B-Q8_0.gguf
  voicevision-server
  ```

## Install

Copy this directory into your vault:

```bash
VAULT=~/Documents/MyVault
mkdir -p "$VAULT/.obsidian/plugins/voicevision"
cp manifest.json main.js "$VAULT/.obsidian/plugins/voicevision/"
```

Then **Settings → Community plugins → Reload plugins** and enable
**voicevision**.

## Commands

| Command | What it does |
|---------|--------------|
| `voicevision: Transcribe audio file` | Asks for a WAV path, sends it to `/transcribe`, inserts the text |
| `voicevision: Ask about selection` | Sends the selection to `/converse`, replaces it with the answer |

Bind either command in **Settings → Hotkeys**.

## Settings

| Setting | Default | Purpose |
|---------|---------|---------|
| Server URL | `http://127.0.0.1:8765` | Local server base URL |
| Bearer token | *(empty)* | Only if the server was started with a token |
| Language | *(empty)* | STT language code (`pt`, `en`, …) |
| Maximum tokens | `512` | Answer length limit |

## Notes

- The plugin uses Obsidian's `requestUrl`, which bypasses browser CORS and
  works with the local server.
- Failures (server down, model missing, unreadable file) appear as an
  Obsidian notice; they never break the editor.
- Desktop-only by design: mobile Obsidian has no filesystem access for the
  audio path.
