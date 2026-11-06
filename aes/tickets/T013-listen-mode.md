---
ticket: T013
title: Listen mode — microfone → STT → texto no stdout
sprint: sprint-02
priority: high
status: done
created: 2026-11-05
---

# T013 — Listen mode — gravar microfone, transcrever, imprimir texto

## Context

O utilizador quer premir um atalho (keybind) no OpenCode e falar, em vez de digitar. O voicevision já tem VAD + STT (whisper.cpp) mas apenas dentro do pipeline completo (VAD → STT → LLM → filtro → TTS). Falta um ponto de entrada "listen-only": capturar áudio do microfone, transcrever via whisper.cpp e imprimir o texto no stdout, sem LLM nem TTS.

Este modo serve de base para um keybind do OpenCode que injete o texto no input do chat. O áudio fica na máquina local (não há servidor de rede — respeita o non-goal do CLAUDE.md).

## Acceptance Criteria

- [ ] Novo ponto de entrada CLI: `python -m voicevision.listen` (ou script `voicevision-listen`) que grava do microfone, transcreve e imprime o texto no stdout.
- [ ] Captura de áudio usa `sounddevice` (extra `audio`), importado lazy — nunca ao nível do módulo (CLAUDE.md never-do).
- [ ] Segmentação reutiliza `WebrtcVadBackend` (já existente, T012).
- [ ] Transcrição reutiliza `WhisperCppBackend` (já existente, T009) — 16 kHz mono PCM16 WAV.
- [ ] Sem LLM, sem TTS, sem pipeline completo.
- [ ] Config via env vars: `VOICEVISION_STT_MODEL`, `VOICEVISION_STT_LANGUAGE`, `VOICEVISION_VAD_*`.
- [ ] Erro claro se `whisper-cli` ou `sounddevice` não estiverem disponíveis (`install_hint`).
- [ ] Testes de unidade com fakes (sem microfone real, sem whisper real).
- [ ] Integração gated atrás de `@pytest.mark.integration` + env var.
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%).

## Scope

**In scope:** `src/voicevision/listen.py`, entry point em `pyproject.toml`, testes em `tests/test_listen.py`.

**Out of scope:** keybind do OpenCode (fora deste repo), câmara/visão (v0.2), servidor HTTP/WebSocket (non-goal), ficheiro de áudio externo (não pedido — o utilizador assume microfone local).

## Dependencies

T009 (whisper_cpp), T012 (vad), `sounddevice` extra, `webrtcvad-wheels` extra.

## Rollback

Remover `src/voicevision/listen.py`, o entry point em `pyproject.toml` e os testes.

## Known Risks

- **Latência:** whisper.cpp demora segundos por utterance. Não é conversação fluida em tempo real.
- **Microfone ausente:** se o OpenCode correr num container/servidor sem `/dev/snd`, a gravação falha. Erro com graça.
- **sounddevice precisa de PortAudio:** falha de importação nativa, não só de Python. Tratar com `install_hint`.
- **VAD pode segmentar mal** respiração/ruído como fala. Ajustar `silence_ms`/`aggressiveness` via env.

## Notes

- Manter import cost baixo: `sounddevice` e `webrtcvad` só importados dentro da função de captura.
- Não tocar em `backends/` nem em `pipeline.py`.

## Implementation notes (done)

Files added:
- `src/voicevision/listen.py` — `ListenConfig`, `load_config()`, `_capture_until_utterance()`, `_transcribe_pcm()`, `run()`, `main()`. Lazy imports of `sounddevice` and `webrtcvad`. Reuses `WebrtcVadBackend`, `WhisperCppBackend`, `pcm16_to_wav`.
- `tests/test_listen.py` — 17 unit tests (env parsing, config loading, capture with fake sounddevice/VAD, transcription with fake child, run orchestration). 1 integration test skipped by default.
- `pyproject.toml` — added `voicevision-listen = "voicevision.listen:main"` entry point.

Verification:
- `pytest tests/test_listen.py` → 17 passed, 1 skipped.
- `ruff check src/voicevision/listen.py tests/test_listen.py` → clean.
- `ruff format --check` → clean.
- `mypy --strict src/voicevision/listen.py` → clean (only pre-existing errors in vad.py/pipeline.py).
- `bandit -r src/voicevision/listen.py` → no issues.

Pre-existing issues not caused by this change:
- `mypy --strict src` fails on vad.py (missing webrtcvad stub) and pipeline.py (missing return annotations).
- `ruff check src tests` has 36 pre-existing findings in piper.py, vad.py, pipeline.py, test_piper.py, test_vad.py, test_pipeline.py.
- `test_import_cost.py` fails because `voicevision` package is not installed in the environment.
