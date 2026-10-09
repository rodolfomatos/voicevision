# voicevision — Operational Contract

This file is the operational contract for AI agents working on this project.
It is the first file an agent must read. It defines scope, boundaries, and evidence rules.

---

## Intent

A reusable Python component ("lego brick") for offline multimodal AI on
Ubuntu and Raspberry Pi. v0.1 scope is the **voice loop**: VAD → speech-to-text
(whisper.cpp) → LLM (qwen3:1.7B via llama.cpp) → output filter → text-to-speech
(piper). Vision returns in v0.2 behind unchanged interfaces.

Architectural decisions are recorded in `docs/ADR-001` (llama.cpp/GGUF for all
model inference) and `docs/ADR-002` (models run as subprocesses, never linked
into this process). Read both before changing anything about backends.

---

## Non-Goals

- Training or fine-tuning models — inference only
- A GUI or user-facing application — this is a library
- Downloading or managing models — operators install them and supply paths
- Serving over the network — no HTTP/gRPC surface of our own
- Cloud APIs — local-first and fully offline at runtime
- Conversation memory or history — the caller owns context
- **Android / Termux / ChaQuopy** — out of scope for v0.1 by operator decision.
  Reopening this is a new project, not a ticket.
- Vision and camera in v0.1 — deferred to v0.2

---

## Critical Files

Any change here must be flagged to the user before proceeding.

- `src/voicevision/core/protocols.py` — the public contract. Changing a method
  signature breaks every backend, including third-party ones.
- `src/voicevision/core/registry.py` — global state; reset between tests
- `src/voicevision/core/config.py` — env var names are user-facing API
- `src/voicevision/backends/subprocess_backend.py` — process lifecycle for all
  model backends. Highest-risk file in the project.
- `docs/ADR-001-backends-llamacpp.md`, `docs/ADR-002-subprocess-backends.md`
- `pyproject.toml`, `.github/workflows/ci.yml`

---

## Never Do

- Never alter test vectors or expected outputs to make tests pass
- Never disable or weaken security checks
- Never commit secrets, API keys, or credentials
- Never modify CI configuration to skip quality gates
- Never hardcode a model path — config or environment only
- Never import a model runtime, `torch`, `cv2`, or `sounddevice` at module
  scope. Lazy import, always.
- Never link a model runtime into this process — subprocesses only (ADR-002)
- Never use `shell=True`. Pass argv lists. `bandit` enforces this.
- Never let model stdout reach a consumer without encoding handling — model
  output is not guaranteed UTF-8
- Never assume a platform beyond Ubuntu 22.04+ / Raspberry Pi OS

---

## Evidence Required

- [ ] `make check` output (docs, code, tests ≥ 80%, ruff, mypy --strict)
- [ ] Proof that no model process spawned during a steady-state call (NFR-3)
- [ ] Diffstory: what changed, why, what was deliberately untouched, residual risk
- [ ] Updated docs if behaviour or scope changed

---

## Review Rule

- AI may implement and suggest.
- Human approves all merges to main.
- No auto-merge without passing all quality gates.

---

## Stable Context (reload each session)

Load at the start of every session:

- `CLAUDE.md` (this file)
- `docs/VISION.md`
- `docs/REQUIREMENTS.md`
- `docs/ROADMAP.md`
- `docs/ADR-001-backends-llamacpp.md`
- `docs/ADR-002-subprocess-backends.md`
- `aes/kanban.md`

---

## Session Context (ephemeral)

- Current ticket file
- Test output
- Diff
- `aes/handoffs/` when resuming interrupted work

---

## Final Response

End every non-trivial task with:

1. **What changed** — files touched and intent
2. **Why** — requirement or finding addressed
3. **Validation performed** — exact command and result, or an explicit
   statement that it was not run
4. **Remaining risk or follow-up** — what was not tested, what to watch

(End of file)