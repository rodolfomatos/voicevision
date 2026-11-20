"""T093 — the emotion benchmark must run without transformers/torch installed."""

from __future__ import annotations

from scripts.benchmark import BenchmarkRunner


def test_benchmark_emotion_reports_accuracy_and_latency() -> None:
    results = BenchmarkRunner(iterations=2).benchmark_emotion()

    accuracy = {
        r.conditions["backend"]: r.value
        for r in results
        if r.metric == "text_accuracy"
    }
    text_latency = [r for r in results if r.metric == "text_detection_latency"]
    audio_latency = [r for r in results if r.metric == "audio_detection_latency"]

    assert accuracy["ml"] == 1.0
    assert accuracy["keyword"] < accuracy["ml"]
    assert len(text_latency) == 2
    assert len(audio_latency) == 2
    assert all(r.value >= 0.0 for r in (*text_latency, *audio_latency))
