---
ticket: T093
title: Emotion Detection Enhancement - ML-based Classification
sprint: M3-skills-intelligence
priority: medium
status: todo
created: 2026-11-20
---

# T093 — Emotion Detection Enhancement

## Context

M3.4 from architecture audit. Current SimpleEmotionBackend uses keyword matching which is very limited. Need ML-based emotion classification for better accuracy.

## Acceptance Criteria

- [ ] ML-based emotion classification (text + audio)
- [ ] Text-based: transformer-based (DistilBERT, BERT) or lightweight (DistilBERT-distilled)
- [ ] Audio-based: wav2vec2, HuBERT, or lightweight (OpenSMILE features + SVM)
- [ ] Multi-label emotion classification (Ekman basic + extended)
- [ ] Confidence scoring for each emotion
- [ ] Real-time capable (text < 50ms, audio < 200ms on CPU)
- [ ] Configurable emotion taxonomy (Ekman 6, Plutchik 8, custom)
- [ ] Unit tests for accuracy, latency
- [ ] Benchmark: accuracy vs keyword-based, latency

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