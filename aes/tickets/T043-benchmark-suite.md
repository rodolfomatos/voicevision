---
ticket: T043
title: Benchmark suite (TTFT, RTF, RSS) (B3)
sprint: sprint-04
priority: medium
status: done
created: 2026-11-13
completed: 2026-11-13
---

# T043 — Benchmark Suite (TTFT, RTF, RSS)

## Context

Need a benchmark suite to measure and track performance metrics across backends:
- **TTFT** (Time To First Token) — latency from request to first token
- **RTF** (Real Time Factor) — synthesis speed relative to audio duration
- **RSS** (Resident Set Size) — memory footprint

## Acceptance Criteria

- [x] `make benchmark` target in Makefile
- [x] `scripts/benchmark.py` with configurable backends
- [x] Measures TTFT (STT + LLM first token), RTF (TTS), RSS
- [x] Outputs JSON summary for CI/CD tracking
- [x] Configurable iterations, warmup runs
- [x] Outputs CSV/JSON for plotting
- [x] `make benchmark` runs in CI (optional models)
- [x] Documents how to interpret results

## Technical Approach

1. `scripts/benchmark.py` with `BenchmarkRunner` class
2. Measures:
   - **TTFT**: Time from request to first token (STT + LLM)
   - **RTF**: Audio duration / synthesis time (TTS)
   - **RSS**: Peak memory during pipeline execution
2. Configurable via CLI args or env vars
3. Outputs JSON + CSV
4. Supports `--dry-run` for CI without models

## Metrics Definitions

- **TTST** (Time To First Token - STT): Time from audio start to transcript
- **TTFT** (Time To First Token - LLM): Time from prompt to first LLM token
- **RTF** (Real Time Factor): Audio duration / synthesis time (lower is better, <1.0 = real-time)
- **RSS** (Resident Set Size): Peak memory in MB

## Dependencies

- Requires models downloaded (`make download-models MODELS=voice-loop`)
- Uses existing `VoicePipeline` and backends
- Optional: `psutil` for RSS measurement

## CI Integration

```yaml
# .github/workflows/benchmark.yml
- run: make benchmark MODELS=voice-loop --output=benchmark.json
```

## Out of Scope

- GPU utilization (future)
- Network latency (local only)
- Multi-user load testing

## Rollback

Disable via `BENCHMARK_ENABLED=false`