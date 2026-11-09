---
ticket: T038
title: VS Code extension (dictate, transcribe file, ask about selection)
sprint: sprint-03
priority: medium
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T038 — VS Code extension

## Context

The README already tells a Linux Mint user to bind `voicevision-listen-and-copy`
to a desktop shortcut and paste into OpenCode. That works, but it is a
detour: record → clipboard → switch window → paste. A VS Code extension can
insert the transcript at the cursor directly, and can use the T035 server for
file transcription and LLM answers.

## Scope decision

The extension is written in **plain JavaScript with no build step**. TypeScript
would add a `tsc` toolchain and a `node_modules` tree to a repository whose
quality gate is Python. Plain CommonJS runs directly in VS Code and is
validated by `node --check`.

Microphone capture stays out of the extension: it shells out to
`voicevision-listen`, which already owns device selection and VAD. The server
is used for the two operations that need no microphone.

## Commands

| Command | Behaviour |
|---------|-----------|
| `voicevision.dictate` | Run `voicevision-listen --quiet`, insert stdout at the cursor |
| `voicevision.transcribeFile` | Pick a WAV file, `POST /transcribe`, insert the transcript |
| `voicevision.ask` | Send the selection to `POST /converse`, insert the answer |

## Acceptance Criteria

- [x] `integrations/vscode/package.json` declares the three commands, `main`,
      engine constraint and configuration keys
- [x] `integrations/vscode/extension.js` implements the three commands with no
      third-party dependency
- [x] `voicevision.serverUrl`, `voicevision.token`, `voicevision.language`,
      `voicevision.listenCommand`, `voicevision.listenArgs` and
      `voicevision.maxTokens` are honoured
- [x] The bearer token is sent as `Authorization` when configured
- [x] Errors are shown with `showErrorMessage`, never thrown into the host
- [x] `integrations/vscode/README.md` documents install, keybindings and the
      server requirement
- [x] `tests/test_integrations.py` validates the manifest, the command list and
      `node --check` on the entry point
- [x] `make check` green

## Out of scope

- Publishing to the VS Code Marketplace
- Audio capture inside the extension
- A status-bar recording indicator

## Dependencies

T035 (HTTP server) for file transcription and answers; `voicevision-listen`
for dictation.

## Rollback

Delete `integrations/vscode/`; no library code changes.

## Known Risks

- `fetch` requires a VS Code version whose Node runtime provides it (VS Code
  1.85+ ships Node 18+). The engine constraint makes this explicit.
- `voicevision-listen` must be on `PATH` of the VS Code process, which on Linux
  desktop is usually the login shell's `PATH`. `voicevision.listenCommand`
  exists for the cases where it is not.

## Implementation notes

- `extension.js` is CommonJS and requires only `vscode`, `child_process` and
  `fs/promises`. No bundler, no `node_modules`, no build step.
- Dictate spawns `voicevision.listenCommand` with `listenArgs`, appending
  `--language` when configured, and inserts stdout at the cursor only when the
  process exits 0 and produced text.
- Transcribe/Ask use `fetch` against `serverUrl`; a non-2xx response is turned
  into `Error(body.error)` so the notification shows the server's message.
- Every command is wrapped by `guarded()`, which converts failures into
  `showErrorMessage` notifications instead of unhandled rejections.
- `tests/test_integrations.py` checks the manifest, the declared/registered
  command names, the configuration keys and runs `node --check` on every `.js`
  file. This is structural validation, not an execution test: VS Code is not
  installed in CI.
