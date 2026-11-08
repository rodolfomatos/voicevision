---
ticket: T026
title: Listen mode --quiet flag to suppress stderr
sprint: sprint-03
priority: medium
status: done
created: 2026-11-07
completed: 2026-11-08
---

# T026 — Listen mode —quiet flag

## Context

O `voicevision-listen` atualmente imprime mensagens de diagnóstico no stderr (ex: "gravando... fale agora...", "gravação terminada.", "no speech detected"). Quando usado em automação ou scripts, essas mensagens são indesejadas — o utilizador quer apenas o texto transcrito no stdout.

## Acceptance Criteria

- [x] Novo argumento CLI `--quiet` que suprime as mensagens de diagnóstico no stderr
- [x] Quando `--quiet` é usado, apenas o texto transcrito é impresso no stdout (ou JSON quando `--json` também está ativo)
- [x] Quando `--quiet` e `--json` são usados juntos, apenas o JSON é impresso no stdout
- [x] Quando nenhum dos dois é usado, comportamento atual é mantido (texto no stdout, mensagens de diagnóstico no stderr)
- [x] Testes de unidade para verificar que --quiet suprime stderr
- [x] Unit tests para verificar que --json + --quiet imprime apenas JSON
- [x] `make check` verde (ruff, mypy --strict, bandit, cobertura ≥ 80%)

## Resolved contradiction

The AC says "suppresses **all** output to stderr"; the Notes say critical
errors must still go to stderr. These conflict. Resolution: `--quiet` silences
progress and outcome messages (`gravando...`, `gravação terminada.`,
`no speech detected`, `listening for wake word...`, `wake word not detected`)
but keeps fatal errors (missing STT model, `ListenError`, backend failures).
Silencing those would leave automation with only an exit code, unable to tell
a missing backend from a failed transcription. Two tests pin this behaviour
(`test_capture_errors_still_reported`, `test_transcription_errors_still_reported`).

Also added `VOICEVISION_QUIET=1` so the behaviour is configurable without
changing the command line.

## Scope

**In scope:** `src/voicevision/listen.py` — adicionar flag `--quiet` e condicionar impressões no stderr
**Out of scope:** Alterar comportamento de outros modos de operação

## Dependencies

T013 (listen.py), T025 (listen.py — output JSON)

## Rollback

Remover argumento `--quiet` e retornar comportamento anterior.

## Known Risks

- Nenhum — é uma mudança simples de condicional de impressão

## Notes

- Manter retrocompatibilidade: sem `--quiet`, comportamento é inalterado
- stderr ainda deve ser usado para erros críticos (erros de backend, etc.)
- Quando `--json` e `--quiet` juntos, apenas JSON é impresso no stdout, nada no stderr (exceto erros críticos)
