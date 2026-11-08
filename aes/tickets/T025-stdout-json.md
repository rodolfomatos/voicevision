---
ticket: T025
title: Saída JSON estruturada para listen mode
sprint: sprint-03
priority: medium
status: done
created: 2026-11-07
completed: 2026-11-08
---

# T025 — Saída JSON estruturada para listen mode

## Context

Atualmente o `voicevision-listen` imprime apenas o texto transcrito no stdout. Para uso em automação e integração com outros programas, é necessário ter uma saída estruturada (JSON) com metadados como timestamp, confiança, latência, etc.

## Acceptance Criteria

- [x] Novo argumento CLI `--json` que faz o listen mode imprimir JSON no stdout
- [x] JSON contém: texto transcrito, timestamp ISO 8601, duração do áudio em segundos, tempo de processamento em ms, língua usada
- [x] Quando `--json` não é passado, comportamento atual (texto puro) é mantido
- [x] Quando `--seconds` é usado com `--json`, inclui duração real gravada
- [x] Quando `--wake-word` é usado com `--json`, inclui se wake word foi detectada
- [x] Unit tests para output JSON válido
- [x] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)

## Deviation from the original AC

- **Whisper version removed from the JSON payload.** `WhisperCppBackend` does
  not expose its version and obtaining it would require an extra
  `whisper-cli --version` subprocess per transcription. The field was dropped
  rather than faked; add it in a future ticket if a consumer needs it.

## Scope

**In scope:** `src/voicevision/listen.py` — adicionar suporte a saída JSON
**Out of scope:** Salvar histórico em arquivo (T027), enviar para servidor HTTP (T035)

## Dependencies

T013 (listen.py)

## Rollback

Remover `--json` flag e lógica de formatação JSON.

## Known Risks

- Nenhum — é apenas mudança de formato de saída, não afeta lógica de captura ou transcrição

## Notes

- Manter retrocompatibilidade: sem `--json`, comportamento é inalterado
- Timestamp deve usar formato ISO 8601 (ISO 8601: YYYY-MM-DDTHH:MM:SS)
- Latência deve ser medida em milissegundos com precisão de casa decimal
