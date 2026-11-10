---
ticket: T027
title: "Preflight: 2026-11-09 — 237d7b2 fix: Piper TTS model and config (voice.onnx, voice.onnx.json)"
phase: ticket
status: done
sprint: backlog
priority: medium
created: '2026-11-09'
requires: []
produces:
  - aes/tickets/T027-preflight.md
blocked_by: ''
---

# T027 — Preflight: 2026-11-09

## Context
Automated preflight check triggered by pipeline at 2026-11-09T17:58:04+00:00.

## Skills Checked
  ✅ aes (contract valid)
  ✅ aes-access-log (contract valid)
  ✅ aes-agent (contract valid)
  ✅ aes_asreview (contract valid)
  ✅ aes-build (contract valid)
  ✅ aes-conflict (contract valid)
  ✅ aes-debt (contract valid)
  ✅ aes-debt-rules (contract valid)
  ✅ aes-epistemics (contract valid)
  ✅ aes-fukitol (contract valid)
  ✅ aes-help (contract valid)
  ✅ aes-iterate (contract valid)
  ✅ aes-learn (contract valid)
  ✅ aes-lesson-skill (contract valid)
  ✅ aes-link-suggest (contract valid)
  ✅ aes-memory-health (contract valid)
  ✅ aes-narrative (contract valid)
  ✅ aes-peer-review (contract valid)
  ✅ aes-plan (contract valid)
  ✅ aes-preflight (contract valid)
  ✅ aes-project-manager (contract valid)
  ✅ aes-proof (contract valid)
  ✅ aes-regenerate (contract valid)
  ✅ aes-review (contract valid)
  ✅ aes-self-learn (contract valid)
  ✅ aes-self-run (contract valid)
  ✅ aes-self-ticket (contract valid)
  ✅ aes-sleep (contract valid)
  ✅ aes-sqlite-check (contract valid)
  ✅ aes-token-trace (contract valid)
  ✅ aes-verify (contract valid)
  ✅ aes-wake (contract valid)
  ✅ agent-sort (contract valid)
  ✅ claim-extractor (contract valid)
  ✅ ecc-integration (contract valid)
  ⚠️  feynman-explainer (no skill.yaml)
  ✅ gf-chat (contract valid)
  ✅ gf-commands (contract valid)
  ✅ gf-premise-propagator (contract valid)
  ⚠️  opencode (no skill.yaml)
  ✅ p2s-paper2skills (contract valid)
  ⚠️  paper2skills (no skill.yaml)
  ✅ reflex-learn (contract valid)
  ✅ workspace-surface-audit (contract valid)
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
237d7b2 fix: Piper TTS model and config (voice.onnx, voice.onnx.json)
3c7af80 feat: add aes-conflict skill with conflict detection (T040)
c4a30c6 feat: speaker identification (T034)
674566d feat: emotion detection on transcript (T033)
04964ad feat: auto language detection for STT (T032)
b62b136 feat: multiple wake words support (T031)
1cd7699 feat: mute TTS flag (T029)
3e9d008 feat: custom hotword file with multiple wake words (T028)
4051dc3 feat: Obsidian plugin and Notion export (T039)
fdfd57a feat: VS Code extension for dictation and local LLM (T038)
## Findings
[MAJOR] feynman-explainer missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] opencode missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract
[MAJOR] paper2skills missing skill.yaml contract
  Closure condition: skill.yaml created with valid contract

## Summary
- Skills checked: 44
- Hooks checked: 6
- Findings: 3
- Status: FINDINGS PRESENT
