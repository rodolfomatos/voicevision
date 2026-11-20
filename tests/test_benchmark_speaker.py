"""T092 — the speaker benchmark must run without pyannote/torch installed."""

from __future__ import annotations

from scripts.benchmark import BenchmarkRunner


def test_benchmark_speaker_reports_accuracy_and_latency() -> None:
    results = BenchmarkRunner(iterations=2).benchmark_speaker()

    accuracy = [r.value for r in results if r.metric == "identification_accuracy"]
    latency = [r for r in results if r.metric == "identification_latency"]
    diarization = [r for r in results if r.metric == "diarization_latency"]

    assert accuracy == [1.0]
    assert len(latency) == 4  # match + stream, two iterations
    assert all(r.value >= 0.0 for r in latency)
    assert len(diarization) == 2
    assert all(r.value >= 0.0 for r in diarization)
