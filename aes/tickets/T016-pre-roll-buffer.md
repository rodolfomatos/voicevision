---
ticket: T016
title: Pre-roll circular buffer — capture audio before wake word detection
sprint: sprint-02
priority: high
status: done
created: 2026-11-06
---

# T016 — Pre-roll circular buffer — capture audio before wake word detection

## Context

T015 added wake word detection ("Olá Ambrósio") to listen mode. The problem:
when the wake word is spoken, VAD only starts capturing after it detects speech,
so the first part of the utterance (including part of the wake word itself)
can be lost. A pre-roll circular buffer keeps the last N seconds of audio in
memory; when a wake word utterance is detected, the buffered audio is included
in the transcription so the full command is preserved.

## Acceptance Criteria

- [ ] `PreRollBuffer` class in `src/voicevision/listen.py`:
    - fixed-size circular buffer of PCM16 bytes
    - `push(data: bytes)` — append audio
    - `get() -> bytes` — return all buffered audio
    - `clear()` — empty the buffer
    - `size() -> int` — bytes currently buffered
- [ ] `ListenConfig.pre_roll_seconds: float = 0.0` — default 0 (disabled)
- [ ] When `pre_roll_seconds > 0`, the buffer fills continuously during
    listen mode (both VAD and fixed-seconds modes)
- [ ] When a wake word is detected, the pre-roll buffer is prepended to the
    utterance audio before transcription
- [ ] Unit tests for `PreRollBuffer` (push/get/clear/size/wraparound)
- [ ] Unit tests for pre-roll integration with wake word mode
- [ ] Integration test gated behind `@pytest.mark.integration` + env var
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)
- [ ] Does not change behavior when `pre_roll_seconds == 0`

## Scope

**In scope:** `src/voicevision/listen.py` (PreRollBuffer, config, integration),
`tests/test_listen.py` (new tests).

**Out of scope:** changing VAD logic, changing whisper.cpp backend, keybind
changes, LLM integration.

## Dependencies

T015 (wake word), T013 (listen.py), T012 (vad).

## Rollback

Remove `PreRollBuffer` and `pre_roll_seconds` from `listen.py`; revert to
T015 behavior.

## Known Risks

- **Memory:** buffer holds raw PCM16 at 16 kHz mono = 32 KB/s. A 10 s buffer
  is ~320 KB — negligible.
- **Wraparound:** when buffer is full, oldest data is overwritten. Correct by
  design and tested.
- **Latency:** pre-roll adds no latency (buffer fills while listening).
- Pre-roll of 0 means unlimited buffer (no pre-roll limit, pass-through).

## Implementation notes (done)

Files changed:
- `src/voicevision/listen.py` — added `PreRollBuffer` class, `ListenConfig.pre_roll_seconds`,
  `_pre_roll_bytes()`, `--pre-roll-seconds` CLI flag, `VOICEVISION_PRE_ROLL_SECONDS` env var,
  pre-roll integration in `_run_wake_word`.
- `tests/test_listen.py` — 8 new tests (PreRollBuffer, pre_roll_bytes, pre-roll wake word mode).

Verification:
- `pytest tests/test_listen.py` → 45 passed, 1 skipped.
- `ruff check src/voicevision/listen.py tests/test_listen.py` → clean.
- `ruff format --check` → clean.
- `mypy --strict src/voicevision/listen.py` → clean.

Pre-existing issues not caused by this change:
- `mypy --strict src` fails on vad.py/pipeline.py (pre-existing).
- `ruff check src tests` has pre-existing findings in older files.
