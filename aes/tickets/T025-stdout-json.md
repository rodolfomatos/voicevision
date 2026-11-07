---
ticket: T025
title: Saída JSON estruturada para listen mode
sprint: sprint-03
priority: medium
status: pending
created: 2026-11-07
---

# T025 — Saída JSON estruturada para listen mode

## Context

Atualmente o `voicevision-listen` imprime apenas o texto transcrito no stdout. Para uso em automação e integração com outros programas, é necessário ter uma saída estruturada (JSON) com metadados como timestamp, confiança, latência, etc.

## Acceptance Criteria

- [ ] Novo argumento CLI `--json` que faz o listen mode imprimir JSON no stdout
- [ ] JSON contém: texto transcrito, timestamp ISO 8601, duração do áudio em segundos, tempo de processamento em ms, língua usada, versão do whisper
- [ ] Quando `--json` não é passado, comportamento atual (texto puro) é mantido
- [ ] Quando `--seconds` é usado com `--json`, inclui duração real gravada
- [ ] Quando `--wake-word` é usado com `--json`, inclui se wake word foi detectada
- [ ] Unit tests para output JSON válido
- [ ] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)

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
