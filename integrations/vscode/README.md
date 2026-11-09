# voicevision for VS Code

Dictate into any editor, transcribe an existing WAV file, or ask the local LLM
about the selected text. Everything runs offline against a local
`voicevision-server`; no audio or text leaves the machine.

## Requirements

- VS Code 1.85 or newer
- `voicevision` installed (`pip install -e /path/to/voicevision`)
- For **Dictate**: `voicevision-listen` on `PATH` and a microphone
- For **Transcribe Audio File** and **Ask About Selection**: a running server

  ```bash
  export VOICEVISION_STT_MODEL=/models/whisper-base.bin
  export VOICEVISION_LLM_MODEL=/models/Qwen3-1.7B-Q8_0.gguf
  voicevision-server
  ```

## Install (from source)

```bash
cd integrations/vscode
npm install -g @vscode/vsce   # optional, only for packaging
code --install-extension .
```

Or copy the directory into `~/.vscode/extensions/voicevision-0.1.0/` and
restart VS Code.

## Commands

| Command | What it does |
|---------|--------------|
| `voicevision: Dictate` | Records until silence, inserts the transcript at the cursor |
| `voicevision: Transcribe Audio File` | Picks a `.wav`, sends it to `/transcribe`, inserts the text |
| `voicevision: Ask About Selection` | Sends the selection to `/converse`, inserts the answer |

## Keybindings

`File → Preferences → Keyboard Shortcuts → Open Keyboard Shortcuts (JSON)`:

```json
[
  { "key": "f9", "command": "voicevision.dictate", "when": "editorTextFocus" },
  { "key": "f10", "command": "voicevision.ask", "when": "editorTextFocus && editorHasSelection" }
]
```

## Settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `voicevision.serverUrl` | `http://127.0.0.1:8765` | Local server base URL |
| `voicevision.token` | *(empty)* | Bearer token if the server requires one |
| `voicevision.language` | *(empty)* | STT language code (`pt`, `en`, …) |
| `voicevision.listenCommand` | `voicevision-listen` | Executable used by Dictate |
| `voicevision.listenArgs` | `["--quiet"]` | Arguments for the listen command |
| `voicevision.maxTokens` | `512` | Answer length limit for Ask About Selection |

## Notes

- The extension is plain JavaScript with no build step and no bundled
  dependencies; `node --check extension.js` validates it.
- Errors (server down, model missing, no microphone) appear as VS Code
  notifications instead of being thrown into the host.
