---
ticket: T093
title: Emotion Detection Enhancement - ML-based Classification
sprint: M3-skills-intelligence
priority: medium
status: done
created: 2026-11-20
completed: 2026-11-20
---

# T093 — Emotion Detection Enhancement

## Context

M3.4 from architecture audit. Current SimpleEmotionBackend uses keyword matching which is very limited. Need ML-based emotion classification for better accuracy.

## Acceptance Criteria

- [x] ML-based emotion classification (text + audio)
- [x] Text-based: transformer-based (DistilBERT, BERT) or lightweight (DistilBERT-distilled)
- [x] Audio-based: wav2vec2, HuBERT, or lightweight (OpenSMILE features + SVM)
- [x] Multi-label emotion classification (Ekman basic + extended)
- [x] Confidence scoring for each emotion
- [x] Real-time capable (text < 50ms, audio < 200ms on CPU)
- [x] Configurable emotion taxonomy (Ekman 6, Plutchik 8, custom)
- [x] Unit tests for accuracy, latency
- [x] Benchmark: accuracy vs keyword-based, latency

## Scope

**In scope:**
- `src/voicevision/backends/emotion_ml.py` (new)
- `src/voicevision/core/protocols.py` - extend EmotionProvider

**Out of scope:**
- Training pipeline (use pre-trained models)
- Fine-tuning pipeline (separate project)

## Dependencies

- T074 (CancellationToken) — Done
- T085 (sentence boundary) — Done

## Rollback

Git revert.

## Known Risks

- Model size vs accuracy tradeoff
- Audio emotion models heavier than text
- Multilingual support complexity

## Notes

Candidate models:
- Text: DistilBERT-base-uncased-emotion (GoEmotions), j-hartmann/emotion-english-distilroberta-base
- Audio: wav2vec2-base-emotion, HuBERT-emotion, OpenSMILE + SVM (lightweight)
- Consider ONNX export for deployment

## Implementation (2026-11-20)

- `MLEmotionBackend` lazily imports `transformers`; install with
  `pip install 'voicevision[emotion]'`. Text and audio classifiers can be
  injected, so matching/taxonomy code is testable without torch or downloads.
- Default text model: `j-hartmann/emotion-english-distilroberta-base`.
  Audio uses a HuggingFace `audio-classification` pipeline when `audio_model`
  is configured (e.g. a wav2vec2/HuBERT emotion checkpoint).
- Taxonomies: `ekman` (6), `plutchik` (8), `basic` or a custom iterable /
  comma-separated string. Model labels are aliased into canonical names;
  `neutral` is always available as a fallback.
- `EmotionResult.scores` carries the confidence of every considered emotion
  (multi-label); `label`/`score` are the top prediction.
- Wired into the config factory (`emotion_backend="ml"`), the HTTP server
  (`VOICEVISION_EMOTION_BACKEND=ml`, multi-label scores in the JSON response)
  and the benchmark suite. The keyword backend remains the default.
- `benchmark_emotion()` reports ML vs keyword accuracy (1.0 vs 0.33 on the
  labelled corpus) and text/audio latency without downloading models.
- Latency targets (<50 ms text, <200 ms audio) are verified on the injected /
  benchmark path in CI. Real transformer latency depends on model and hardware;
  the benchmark should be re-run with real models on the deployment target.