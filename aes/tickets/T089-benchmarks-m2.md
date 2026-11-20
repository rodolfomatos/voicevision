---
ticket: T089
title: M2 Benchmarks — VAD, Wake Word, STT, TTS Latency
sprint: M2-realtime-voice
priority: high
status: todo
created: 2026-11-18
---

# T089 — M2 Benchmarks

## Context

M2.5 from architecture audit. Establish baseline metrics for M2 components before and after each improvement.

## Acceptance Criteria

- [ ] Extend `scripts/benchmark.py` with M2 benchmarks:
  - VAD: false positive/negative rate, detection latency (clean + noise)
  - Wake Word: false positive/negative rate, detection latency
  - STT: latency (first token, full), WER (clean + noise)
  - TTS: latency (first audio), RTF (real-time factor)
  - Pipeline: TTFT (time to first token), total latency, interruption latency
- [ ] Dataset: Common Voice (pt/en), CHiME noise corpus
- [ ] Hardware: CI (GitHub Actions), RPi 4, x86_64 laptop
- [ ] Output: JSON + Markdown report with p50/p95/p99
- [ ] CI integration: run on PR, fail on regression > 10%
- [ ] Report: `docs/benchmarks/M2_BASELINE.md`

## Scope

**In scope:**
- `scripts/benchmark.py` — extend
- `scripts/download_test_data.py` — new
- `docs/benchmarks/M2_BASELINE.md`
- CI workflow: `.github/workflows/benchmark.yml`

**Out of scope:**
- Long-form accuracy benchmarks (separate)

## Dependencies

- T085 (sentence boundary) — Done
- T086 (adaptive VAD) — Done
- T087 (barge-in) — Done
- T088 (streaming STT) — Done

## Rollback

Git revert.

## Known Risks

- Benchmark flakiness on CI (audio device variability)
- Dataset download size (~2GB)
- RPi 4 not available in GitHub Actions (x86 only)

## Notes

Use `scripts/benchmark.py` as base. Add `--device` flag for hardware selection.