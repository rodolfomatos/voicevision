---
ticket: T027
title: Persistent transcript history (~/.voicevision/history.jsonl)
sprint: sprint-03
priority: medium
status: done
created: 2026-11-08
completed: 2026-11-08
---

# T027 — Persistent transcript history

## Context

Listen mode prints each transcript and forgets it. Users need a durable,
machine-readable record of what was said for later search, auditing and
integration (T035 server, T039 Obsidian/Notion export). A JSON Lines file is
append-only, trivially parseable, and safe against partial writes.

## Acceptance Criteria

- [x] New module `voicevision.history` with `HistoryEntry` and `HistoryStore`
- [x] Every successful transcription in `voicevision-listen` appends one JSON
      object per line to `~/.voicevision/history.jsonl`
- [x] Each entry contains `timestamp` (ISO 8601), `transcript`, `language`,
      `audio_duration_seconds`, `transcription_ms`, `wake_word` (nullable)
- [x] Parent directory is created with mode `0700`; the file is created with
      mode `0600`
- [x] `VOICEVISION_HISTORY_FILE` overrides the path; `VOICEVISION_HISTORY_ENABLED=0`
      disables persistence
- [x] CLI flags `--no-history` and `--history-file PATH`
- [x] History write failures never break transcription: they emit a warning on
      stderr (unless `--quiet`) and the exit code stays 0
- [x] `python -m voicevision.history` lists entries as a table; `--clear` empties
      the file after confirmation-free explicit flag
- [x] Unit tests for append, read, malformed-line tolerance, permissions,
      disabled mode and write-failure tolerance
- [x] `make check` green (ruff, mypy --strict, bandit, coverage ≥ 80%)

## Scope

**In scope:** new `history.py`, integration in `listen.py`, docs, tests.
**Out of scope:** rotation/retention policy, encryption at rest, remote sync.

## Dependencies

T013 (listen mode), T025 (JSON output shares the same metadata).

## Rollback

Remove the module and the `_record_history()` call in `listen.run()`; delete
`~/.voicevision/history.jsonl` manually.

## Known Risks

- Transcripts are sensitive personal data written to disk. Mitigated with
  `0600` permissions, a documented path, and an opt-out flag.
- A full disk or read-only home directory must not break dictation. Writes are
  best-effort and caught.
- Concurrent writers can interleave partial lines. Mitigated by writing each
  entry with a single `write()` of a complete line plus `\n`.

## Notes

- JSON Lines (not a JSON array) so appends never rewrite the whole file.
- Malformed lines are skipped on read instead of raising: the file is
  append-only and may be edited by hand.
