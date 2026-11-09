---
ticket: T039
title: Obsidian plugin and Notion export
sprint: sprint-03
priority: medium
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T039 — Obsidian plugin and Notion export

## Context

Notes are where transcripts end up. Two integrations close the loop:

- **Obsidian**: a desktop plugin that transcribes a WAV file or asks the local
  LLM about the current selection, inserting the result at the cursor.
- **Notion**: a CLI that exports a transcript (or an audio file transcribed
  locally) into a Notion page.

Both reuse the T035 server. Obsidian talks to it with `requestUrl`; Notion uses
`voicevision.client` for the local calls and the Notion HTTP API for the export.

## Scope decision

Obsidian plugins are JavaScript and are loaded by Obsidian, not Node. The
plugin is written in plain CommonJS with no build step, like the VS Code
extension (T038), so `node --check` is a meaningful gate.

Notion is a **cloud** service, which the project otherwise avoids. This is an
explicit export step chosen by the operator: inference stays local, and only
the finished text the operator asks to export is sent to Notion. The Notion
token is read from the environment and never logged.

## Acceptance Criteria

- [x] `integrations/obsidian/manifest.json` is valid and marks the plugin
      desktop-only
- [x] `integrations/obsidian/main.js` implements:
      `transcribe-audio-file` and `ask-about-selection`
- [x] The plugin has a settings tab for `serverUrl`, `token`, `language` and
      `maxTokens`
- [x] The plugin inserts results with `editor.replaceSelection` and reports
      failures with `new Notice(...)`
- [x] `integrations/notion/voicevision_notion.py` exports a transcript to a
      Notion page, using `--audio` (transcribe locally) or `--text-file`
- [x] The Notion token comes from `NOTION_TOKEN`; the module never logs it
- [x] Notion blocks are split so each stays under the API's 2000-character
      limit
- [x] Pure helpers (`build_page_payload`, `split_text`) are unit-tested
- [x] `tests/test_integrations.py` validates both integrations structurally
- [x] `make check` green

## Out of scope

- Obsidian mobile support (the plugin is desktop-only)
- Bi-directional Notion sync
- OAuth for Notion (an internal integration token is enough)

## Dependencies

T035 (HTTP server), T037 (`voicevision.client`).

## Rollback

Delete `integrations/obsidian/` and `integrations/notion/`; no library code
changes.

## Known Risks

- Notion's block API caps rich-text content at 2000 characters per block. The
  exporter splits on paragraph boundaries first, then hard-splits.
- The Obsidian plugin reads files with Node's `fs`, so it is desktop-only by
  construction.
- Notion export is the only path in this repository that contacts a cloud
  service; it is opt-in and documented as such.

## Implementation notes

- `integrations/obsidian/main.js` is plain CommonJS, desktop-only
  (`isDesktopOnly: true`). It registers `transcribe-audio-file` and
  `ask-about-selection`, a `PluginSettingTab` for `serverUrl`, `token`,
  `language` and `maxTokens`, and uses `requestUrl` so the local server works
  without CORS. Results are inserted with `editor.replaceSelection`; every
  failure becomes `new Notice(...)`.
- The audio path is typed into a small `PathModal` rather than a native file
  picker: Obsidian has no file dialog API, and the operator path is documented
  in the README.
- `integrations/notion/voicevision_notion.py` is a standalone CLI. It imports
  `voicevision.client` for the local transcription step, then POSTs the page
  payload to `https://api.notion.com/v1/pages`. The token is read from
  `NOTION_TOKEN` only when actually exporting (`--dry-run` needs no token) and
  is never printed.
- `split_text` prefers a newline, then a space, then a hard cut, so every block
  stays under Notion's 2000-character rich-text cap. `build_page_payload`
  selects `title` for a page parent and `Name` for a database parent unless
  `--title-property` is given.
- `tests/test_notion_export.py` loads the module from its path (it is outside
  the package) and tests the pure helpers plus the request/response handling
  with a monkeypatched `urlopen`; no network call is made.
  `tests/test_integrations.py` adds `TestObsidian` and `TestNotion` structural
  checks and keeps the `node --check` gate for both JavaScript entry points.
