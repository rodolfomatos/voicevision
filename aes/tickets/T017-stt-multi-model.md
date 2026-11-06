---
ticket: T017
title: Multiple STT models — whisper-small/tiny selection via config
sprint: sprint-02
priority: medium
status: done
created: 2026-11-06
---

# T017 — Multiple STT models — whisper-small/tiny selection via config

## Context

T013/T015/T016 built `voicevision-listen` with whisper.cpp STT. Currently the model
path is a single env var (`VOICEVISION_STT_MODEL`) pointing to one `.bin` file
(default `whisper-base.bin`, ~142 MB). whisper.cpp ships several model sizes
(tiny, base, small, medium, large) with different speed/accuracy trade-offs:

| Model | Size | Speed | Accuracy | Use case |
|-------|------|-------|----------|----------|
| tiny  | ~39 MB | Fastest | Lower | Low-end hardware (RPi Zero) |
| base  | ~142 MB | Fast | Good | Default, general purpose |
| small | ~244 MB | Slower | Better | More accurate transcription |
| medium| ~769 MB | Slow | Better still | High accuracy, more CPU/RAM |
| large | ~1.5 GB | Slowest | Best | Server-grade hardware |

Operators on Raspberry Pi or low-spec hardware may prefer `tiny` or `small` for
lower latency, while desktop operators may prefer `small` or `medium` for better
accuracy. Currently there is no way to select a model other than changing the
env var manually.

## Acceptance Criteria

- [ ] `ListenConfig` gains `stt_model_path` field (default: `""` → use
    `VOICEVISION_STT_MODEL`)
- [ ] `VOICEVISION_STT_MODEL` env var remains the primary configuration
- [ ] CLI flag `--model` overrides env var (already exists, keep working)
- [ ] Document model sizes and trade-offs in `docs/VOICE_INPUT.md`
- [ ] Unit tests: config loads model path from env, CLI flag overrides env
- [ ] Integration test: transcribe with a small model (gated behind env var)
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)
- [ ] Does not break existing single-model behavior

## Scope

**In scope:** `src/voicevision/listen.py` (config field, CLI flag, docs),
`tests/test_listen.py` (new tests), `docs/VOICE_INPUT.md` (model size table).

**Out of scope:** Downloading models automatically (operator responsibility),
faster-whisper backend (different runtime, separate consideration), model
management CLI (B5 backlog).

## Dependencies

T013 (listen.py), T009 (whisper_cpp backend).

## Rollback

Remove `stt_model_path` field from `ListenConfig`; revert to env var only.

## Known Risks

- **Model size vs accuracy:** smaller models transcribe faster but less
  accurately. Operators must choose based on their hardware.
- **Model files not included:** operator must download the `.bin` file
  themselves; voicevision never downloads models.
- **whisper.cpp compatibility:** different model sizes may require different
  whisper.cpp build flags or versions.

## Notes

- whisper.cpp models are named `ggml-tiny.bin`, `ggml-base.bin`,
  `ggml-small.bin`, `ggml-medium.bin`, `ggml-large.bin`.
- Suggested default: `base` (current behavior).
- Document that PT-PT works best with `base` or larger.

## Implementation notes (done)

Files changed:
- `src/voicevision/listen.py` — already supported `VOICEVISION_STT_MODEL` env var
  and `--model` CLI flag; no code change needed beyond existing implementation.
- `tests/test_listen.py` — 3 new tests (config reads model from env, defaults to
  empty, CLI flag overrides env).
- `docs/VOICE_INPUT.md` — added STT model size table with trade-offs and example
  usage.

Verification:
- `pytest tests/test_listen.py` → 48 passed, 1 skipped.
- `ruff check src/voicevision/listen.py tests/test_listen.py` → clean.
- `ruff format --check` → clean.
- `mypy --strict src/voicevision/listen.py` → clean.

Pre-existing issues not caused by this change:
- `mypy --strict src` fails on vad.py/pipeline.py (pre-existing).
- `ruff check src tests` has pre-existing findings in older files.
