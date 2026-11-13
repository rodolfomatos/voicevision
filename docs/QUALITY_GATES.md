# Quality Gates

All gates run via `make check`. Extend this file with domain-specific gates.

## Pre-flight gate (AES pre-flight)

| Gate | Command | Failure Action |
|------|---------|----------------|
| Pre-flight | `make aes-preflight` | BLOCKER — skills, hooks, pipeline config, recent commits verified |
| Quality gate | `make check` | BLOCKER — all sub-gates must pass |

## Quality Gates (AES)

| Gate | Command | Failure Action |
|------|---------|----------------|
| Docs check | `make docs-check` | BLOCKER — docs missing or stale sections |
| Code check | `make code-check` | BLOCKER — TODO/FIXME comments, structure issues |
| Test check | `make test-check` | BLOCKER — coverage < 80% |
| Lint check | `make lint-check` | BLOCKER — ruff, mypy --strict, bandit errors |

## AES Epistemics gates

| Gate | Command | Failure Action |
|------|---------|----------------|
| GMIF check | `make gmif-check` | BLOCKER — island graph UNSAT with high-confidence core |
| GMIF staleness | `make gmif-staleness` | BLOCKER — active ticket references STALE shadow |

## AES Conflict check

| Gate | Command | Failure Action |
|------|---------|----------------|
| Conflict check | `make aes-conflict` | BLOCKER — orphan access, epistemic contradiction, causality violation, session conflict, stale ticket |

## Adding Domain Gates

Add sections below for frontend, backend, infrastructure, or custom gates.

## Gate semantics

- **BLOCKER**: stops the pipeline immediately; must be fixed before commit.
- **MAJOR**: must be resolved before the next sprint.
- **MINOR**: fix when convenient, but track in backlog.
- **WARN**: informational only; review recommended.

## Pre-flight checks (AES preflight skill)

The pre-flight skill introspects installed skills, pipeline hooks, configuration,
and recent commits to verify pipeline health before execution:

1. **Skills check**: every skill in `~/.config/opencode/skills/` must have a valid
   `SKILL.md` contract file.
2. **Hooks check**: every hook in `aes/hooks/` must be executable.
3. **Configuration check**: configuration files diverge from expected state.
4. **Recent commits check**: recent commits are checked for pipeline violations.

The pre-flight gate runs automatically as part of `make check` via the
pre-commit hook.

## Example failure output

```
═════════════════════════════════════════════════════════════════════════════
  Verification Gate — T044
  File: T044-onnx-runtime-vision.md
═══════════════════════════════════════════════════

  ✅ (already checked) New module `src/voicevision/backends/onnx_vision.py` with:
  ✅ (already checked) `OnnxVisionBackend` class
  ✅ (already checked) `available()` returns True
  ✅ (already checked) `describe(image, question)` returns str
  ✅ (already checked) `close()` method exists
  ✅ (already checked) `PipelineConfig.vision_backend` field exists
  ✅ (already checked) `VoiceVisionService.vision` instantiates correct backend
  ✅ (already checked) Unit tests cover backend with mock ONNX session
  ✅ (already checked) `make check` green

────────────────────────────────────────────────────
  Result: 8 passed, 0 failed, 8 total
────────────────────────────────────────────────────
```
