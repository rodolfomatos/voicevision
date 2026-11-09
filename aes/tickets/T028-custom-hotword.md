---
ticket: T028
title: Custom hotword file (JSON config for multiple wake words)
sprint: sprint-04
priority: medium
status: done
created: 2026-11-09
completed: 2026-11-09
---

# T028 — Custom hotword file

## Context

The wake word "Olá Ambrósio" is currently hardcoded in `listen.py`. Users want
to configure their own wake words, including multiple alternatives. A JSON
file at `~/.voicevision/hotwords.json` (and an env var override) will define
the list of wake words and their thresholds.

## Acceptance Criteria

- [x] New file `src/voicevision/core/hotwords.py` with:
    - `HotwordConfig` dataclass: `words: list[str]`, `threshold: float` (default 0.5)
    - `load_hotwords(path: Path | None, env_var: str | None) -> HotwordConfig`
    - Default: `["Olá Ambrósio"]` with threshold 0.5
- [x] Environment variable `VOICEVISION_HOTWORDS` points to a JSON file
- [x] JSON format:
    ```json
    {
      "words": ["Olá Ambrósio", "Hey Ambrósio"],
      "threshold": 0.5
    }
    ```
- [x] `ListenConfig` gains `hotwords: HotwordConfig` field
- [x] `voicevision-listen` uses the configured words (substring match on
  transcript, case-insensitive)
- [x] Multiple words: any match triggers wake word mode
- [x] Tests cover loading from file, env var, default, and invalid JSON
- [x] `make check` green

## Out of scope

- Per-word thresholds (single threshold for all)
- Hotword training / model switching

## Dependencies

T015 (wake word), T027 (history), T030 (continuous mode).

## Rollback

Delete `src/voicevision/core/hotwords.py`; revert `ListenConfig` change.
## Implementation notes

- New module `src/voicevision/core/hotwords.py` with `HotwordConfig` dataclass
  and `load_hotwords()` / `wake_words_detected()` functions.
- `ListenConfig` now has `hotwords: HotwordConfig` field instead of
  `wake_word: str`. Default is empty list (no wake word), maintaining
  backward compatibility with single-shot mode.
- Environment variable `VOICEVISION_HOTWORDS` points to a JSON file with
  `{"words": [...], "threshold": 0.5}`. Legacy `VOICEVISION_WAKE_WORD`
  still works and replaces the first word in the list.
- CLI adds `--hotwords-file` and `--wake-word` (replaces first word).
- Wake word matching is case-insensitive and accent-insensitive via NFD
  normalization. Multiple words: any match triggers.
- JSON output includes `wake_word` (first configured word) and
  `wake_word_detected` boolean.
- Continuous mode logs all configured words and detects any of them.
- History records the specific matched word.
- Tests updated for new API; backward compatibility maintained.
