---
ticket: T016
title: "Preflight: 2026-11-09 — c4a30c6 feat: speaker identification (T034)"
phase: ticket
status: done
sprint: backlog
priority: medium
created: '2026-11-09'
requires: []
produces:
  - aes/tickets/T016-preflight.md
blocked_by: ''
---

# T016 — Preflight: 2026-11-09

## Context
Automated preflight check triggered by pipeline at 2026-11-09T14:12:07+00:00.

## Skills Checked
  ⚠️  aes (no skill.yaml)
  ⚠️  aes-access-log (no skill.yaml)
  ⚠️  aes-agent (no skill.yaml)
  ⚠️  aes_asreview (no skill.yaml)
  ⚠️  aes-build (no skill.yaml)
  ⚠️  aes-conflict (no skill.yaml)
  ⚠️  aes-debt (no skill.yaml)
  ⚠️  aes-debt-rules (no skill.yaml)
  ⚠️  aes-epistemics (no skill.yaml)
  ⚠️  aes-fukitol (no skill.yaml)
  ⚠️  aes-help (no skill.yaml)
  ⚠️  aes-iterate (no skill.yaml)
  ⚠️  aes-learn (no skill.yaml)
  ⚠️  aes-lesson-skill (no skill.yaml)
  ⚠️  aes-link-suggest (no skill.yaml)
  ⚠️  aes-memory-health (no skill.yaml)
  ⚠️  aes-narrative (no skill.yaml)
  ⚠️  aes-peer-review (no skill.yaml)
  ⚠️  aes-plan (no skill.yaml)
  ⚠️  aes-preflight (no skill.yaml)
  ⚠️  aes-project-manager (no skill.yaml)
  ⚠️  aes-proof (no skill.yaml)
  ⚠️  aes-regenerate (no skill.yaml)
  ⚠️  aes-review (no skill.yaml)
  ⚠️  aes-self-learn (no skill.yaml)
  ⚠️  aes-self-run (no skill.yaml)
  ⚠️  aes-self-ticket (no skill.yaml)
  ⚠️  aes-sleep (no skill.yaml)
  ⚠️  aes-sqlite-check (no skill.yaml)
  ⚠️  aes-token-trace (no skill.yaml)
  ⚠️  aes-verify (no skill.yaml)
  ⚠️  aes-wake (no skill.yaml)
  ⚠️  agent-sort (no skill.yaml)
  ⚠️  claim-extractor (no skill.yaml)
  ⚠️  ecc-integration (no skill.yaml)
  ⚠️  feynman-explainer (no skill.yaml)
  ⚠️  gf-chat (no skill.yaml)
  ⚠️  gf-commands (no skill.yaml)
  ⚠️  gf-premise-propagator (no skill.yaml)
  ⚠️  opencode (no skill.yaml)
  ⚠️  p2s-paper2skills (no skill.yaml)
  ⚠️  paper2skills (no skill.yaml)
  ⚠️  reflex-learn (no skill.yaml)
  ⚠️  workspace-surface-audit (no skill.yaml)
  Total skills: 44

## Hooks Checked
  ✅ pre-build-gf.sh (executable)
  ✅ pre-build.sh (executable)
  ✅ pre-commit.sh (executable)
  ✅ pre-merge.sh (executable)
  ✅ pre-review.sh (executable)
  ✅ pre-verify.sh (executable)
  Total hooks: 6

## Recent Commits (last 10)
c4a30c6 feat: speaker identification (T034)
674566d feat: emotion detection on transcript (T033)
04964ad feat: auto language detection for STT (T032)
b62b136 feat: multiple wake words support (T031)
1cd7699 feat: mute TTS flag (T029)
3e9d008 feat: custom hotword file with multiple wake words (T028)
4051dc3 feat: Obsidian plugin and Notion export (T039)
fdfd57a feat: VS Code extension for dictation and local LLM (T038)
ebbfb41 feat: stdlib API client and Home Assistant integration (T037)
6754f10 feat: WebSocket streaming endpoint (T036)
## Findings
[MAJOR] aes missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-access-log missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-agent missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes_asreview missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-build missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-conflict missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-debt missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-debt-rules missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-epistemics missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-fukitol missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-help missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-iterate missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-learn missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-lesson-skill missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-link-suggest missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-memory-health missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-narrative missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-peer-review missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-plan missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-preflight missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-project-manager missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-proof missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-regenerate missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-review missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-self-learn missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-self-run missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-self-ticket missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-sleep missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-sqlite-check missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-token-trace missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-verify missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] aes-wake missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] agent-sort missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] claim-extractor missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] ecc-integration missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] feynman-explainer missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] gf-chat missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] gf-commands missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] gf-premise-propagator missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] opencode missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] p2s-paper2skills missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] paper2skills missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] reflex-learn missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] workspace-surface-audit missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract

## Summary
- Skills checked: 44
- Hooks checked: 6
- Findings: 44
- Status: FINDINGS PRESENT
