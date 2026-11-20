"""T094 — duplex benchmark must report ERLE and barge-in latency without hardware."""

from __future__ import annotations

from scripts.benchmark import BenchmarkRunner


def test_benchmark_duplex_reports_erle_and_barge_in_latency() -> None:
    results = BenchmarkRunner(iterations=3).benchmark_duplex()

    erle = [r for r in results if r.metric == "echo_return_loss_enhancement"]
    latency = [r for r in results if r.metric == "barge_in_latency"]

    assert len(erle) == 3  # one per configured cancellation strength
    assert len(latency) == 3
    assert {r.conditions["aec_strength"] for r in erle} == {0.25, 0.5, 0.75}
    # A real echo path must be suppressed by at least 12 dB in every config.
    assert all(r.value > 12.0 for r in erle), [r.value for r in erle]
    # Interruption latency budget is 50 ms end to end.
    assert all(r.value < 50.0 for r in latency), [r.value for r in latency]
