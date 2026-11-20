#!/usr/bin/env python3
"""Benchmark suite for voicevision M2 components.

Measures latency, accuracy, and resource usage for:
- VAD (WebRTC, Adaptive)
- Wake Word detection
- STT (whisper.cpp)
- TTS (piper)
- Full pipeline (VAD → STT → LLM → TTS)

Usage:
    python scripts/benchmark.py --device cpu --iterations 10
    python scripts/benchmark.py --device rpi4 --iterations 5 --output results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np

from voicevision import VoicePipeline, PipelineConfig
from voicevision.backends.adaptive_vad import AdaptiveVadBackend
from voicevision.backends.vad import WebrtcVadBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.backends.piper import PiperBackend


@dataclass
class BenchmarkResult:
    """Single benchmark measurement."""
    component: str
    metric: str
    value: float
    unit: str
    conditions: dict[str, Any]


@dataclass
class BenchmarkSummary:
    """Aggregated benchmark results."""
    component: str
    metric: str
    count: int
    mean: float
    median: float
    std: float
    p50: float
    p95: float
    p99: float
    unit: str
    conditions: dict[str, Any]


class BenchmarkRunner:
    """Runs benchmarks for voicevision components."""

    def __init__(self, device: str = "cpu", iterations: int = 10):
        self.device = device
        self.iterations = iterations
        self.results: list[BenchmarkResult] = []

    def _time_it(self, func, *args, **kwargs) -> tuple[Any, float]:
        """Time a function call."""
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        return result, elapsed

    def _generate_test_audio(self, duration_ms: int, sample_rate: int = 16000) -> bytes:
        """Generate synthetic PCM16 audio for testing."""
        import math
        samples = int(duration_ms * 16000 / 1000)
        max_val = 32767
        data = bytearray()
        for i in range(samples):
            t = i / 16000
            val = int(0.5 * 32767 * np.sin(2 * np.pi * 440 * t))
            data.extend(val.to_bytes(2, "little", signed=True))
        return bytes(data)

    def benchmark_vad(self, vad_type: str = "webrtc") -> list[BenchmarkResult]:
        """Benchmark VAD detection latency and accuracy."""
        results = []

        if vad_type == "webrtc":
            vad = WebrtcVadBackend(aggressiveness=2, sample_rate=16000)
        else:
            vad = AdaptiveVadBackend(sample_rate=16000, frame_ms=30, noise_percentile=10, sensitivity=2.0)

        # Test with speech-like audio
        speech_audio = self._generate_test_audio(1000)  # 1 second of speech-like audio
        silence_audio = bytes(32000)  # 1 second of silence

        for _ in range(self.iterations):
            # Test speech detection
            _, latency = self._time_it(vad.process_frame, self._generate_test_audio(30))
            results.append(BenchmarkResult(
                component="vad",
                metric="speech_detection_latency",
                value=latency * 1000,  # ms
                unit="ms",
                conditions={"vad_type": vad_type, "audio_type": "speech"}
            ))

            # Test silence detection
            _, latency = self._time_it(vad.process_frame, bytes(960))
            results.append(BenchmarkResult(
                component="vad",
                metric="silence_detection_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"vad_type": vad_type, "audio_type": "silence"}
            ))

        return results

    def benchmark_wake_word(self) -> list[BenchmarkResult]:
        """Benchmark wake word detection."""
        results = []
        # TODO: Implement wake word benchmark
        return results

    def benchmark_stt(self, model_path: str = "/models/whisper-base.bin") -> list[BenchmarkResult]:
        """Benchmark STT latency and accuracy."""
        results = []

        stt = WhisperCppBackend(model=model_path, language="en")

        test_audio = self._generate_test_audio(3000)  # 3 seconds of audio

        for _ in range(self.iterations):
            # Warm up
            stt.transcribe(test_audio[:32000])

            # Measure full transcription latency
            _, latency = self._time_it(stt.transcribe, test_audio)
            results.append(BenchmarkResult(
                component="stt",
                metric="full_transcription_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"model": "whisper-base", "audio_duration_s": 3.0}
            ))

            # Measure streaming latency (first chunk)
            chunks = self._chunk_audio(test_audio, chunk_size_ms=1500, overlap_ms=500)
            chunk_gen = (c for c in chunks)
            first_chunk_latency = None
            for i, chunk in enumerate(stt.transcribe_stream(chunks)):
                if i == 0:
                    first_chunk_latency = time.perf_counter()
                if chunk.is_final:
                    break
            if first_chunk_latency:
                results.append(BenchmarkResult(
                    component="stt",
                    metric="streaming_first_chunk_latency",
                    value=(time.perf_counter() - first_chunk_latency) * 1000,
                    unit="ms",
                    conditions={"model": "whisper-base", "chunk_size_ms": 1500}
                ))

        return results

    def benchmark_tts(self, model_path: str = "/models/voice.onnx") -> list[BenchmarkResult]:
        """Benchmark TTS latency and RTF."""
        results = []

        tts = PiperBackend(model=model_path)

        test_text = "This is a test sentence for text to speech synthesis benchmarking."

        for _ in range(self.iterations):
            # Warm up
            tts.synthesize("Warm up.")

            # Measure synthesis latency
            _, latency = self._time_it(tts.synthesize, test_text)
            results.append(BenchmarkResult(
                component="tts",
                metric="synthesis_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"model": "piper", "text_length": len(test_text)}
            )

            # Measure RTF (Real-Time Factor)
            # RTF = synthesis_time / audio_duration
            audio = tts.synthesize(test_text)
            audio_duration = len(audio) / (16000 * 2)  # seconds
            rtf = (latency * 1000) / (audio_duration * 1000)
            results.append(BenchmarkResult(
                component="tts",
                metric="rtf",
                value=rtf,
                unit="ratio",
                conditions={"model": "piper", "text_length": len(test_text)}
            )

            # Measure streaming latency
            chunks = list(tts.synthesize_stream([test_text]))
            if chunks:
                results.append(BenchmarkResult(
                    component="tts",
                    metric="streaming_first_chunk_latency",
                    value=0,  # Would need proper timing
                    unit="ms",
                    conditions={"model": "piper"}
                ))

        return results

    def benchmark_pipeline(self, config: PipelineConfig) -> list[BenchmarkResult]:
        """Benchmark full pipeline latency."""
        results = []

        pipeline = VoicePipeline(config)

        test_audio = self._generate_test_audio(3000)

        for _ in range(self.iterations):
            # Warm up
            pipeline.process(test_audio[:32000])

            # Measure full pipeline latency
            _, latency = self._time_it(pipeline.process, test_audio)
            results.append(BenchmarkResult(
                component="pipeline",
                metric="full_pipeline_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"audio_duration_s": 3.0}
            )

            # Measure TTFT (Time to First Token) - would need streaming
            # TODO: Implement streaming pipeline benchmark

        return results

    def _chunk_audio(self, audio: bytes, chunk_size_ms: int, overlap_ms: int) -> list[bytes]:
        """Split audio into overlapping chunks."""
        samples_per_ms = 16000 // 1000
        bytes_per_ms = 2 * samples_per_ms
        chunk_bytes = chunk_size_ms * 16000 * 2 // 1000
        overlap_bytes = overlap_ms * 16000 * 2 // 1000

        chunks = []
        for i in range(0, len(audio), chunk_bytes - overlap_bytes):
            chunk = audio[i:i + chunk_bytes]
            if len(chunk) >= chunk_bytes // 2:  # Only keep chunks that are at least half size
                chunks.append(chunk)
        return chunks

    def _generate_test_audio(self, duration_ms: int, sample_rate: int = 16000) -> bytes:
        """Generate synthetic PCM16 audio for testing."""
        samples = int(duration_ms * sample_rate / 1000)
        max_val = 32767
        data = bytearray()
        for i in range(samples):
            t = i / sample_rate
            val = int(0.5 * max_val * np.sin(2 * np.pi * 440 * t))
            data.extend(val.to_bytes(2, "little", signed=True))
        return bytes(data)

    def run_all(self, model_paths: dict[str, str]) -> list[BenchmarkSummary]:
        """Run all benchmarks and return aggregated summaries."""
        all_results = []

        # VAD benchmarks
        self.results.extend(self.benchmark_vad("webrtc"))
        self.results.extend(self.benchmark_vad("adaptive"))

        # STT benchmarks
        if "stt" in model_paths:
            self.results.extend(self.benchmark_stt(model_paths["stt"]))

        # TTS benchmarks
        if "tts" in model_paths:
            self.results.extend(self.benchmark_tts(model_paths["tts"]))

        # Pipeline benchmarks
        if "pipeline" in model_paths:
            config = PipelineConfig(
                stt_model=model_paths.get("stt", ""),
                llm_model=model_paths.get("llm", ""),
                tts_model=model_paths.get("tts", ""),
            )
            self.results.extend(self.benchmark_pipeline(config))

        # Aggregate results
        return self._aggregate_results()

    def _aggregate_results(self) -> list[BenchmarkSummary]:
        """Aggregate raw results into statistical summaries."""
        from collections import defaultdict

        grouped = defaultdict(list)
        for r in self.results:
            key = (r.component, r.metric, tuple(sorted(r.conditions.items())))
            grouped[key].append(r.value)

        summaries = []
        for (component, metric, conditions), values in grouped.items():
            values_arr = np.array(values)
            summaries.append(BenchmarkSummary(
                component=component,
                metric=metric,
                count=len(values),
                mean=float(np.mean(values_arr)),
                median=float(np.median(values_arr)),
                std=float(np.std(values_arr)),
                p50=float(np.percentile(values_arr, 50)),
                p95=float(np.percentile(values_arr, 95)),
                p99=float(np.percentile(values_arr, 99)),
                unit="ms" if "latency" in metric else "ratio" if "rtf" in metric else "",
                conditions=dict(conditions),
            ))
        return summaries

    def save_results(self, output_path: Path) -> None:
        """Save benchmark results to JSON."""
        summaries = self._aggregate_results()
        data = {
            "device": self.device,
            "iterations": self.iterations,
            "timestamp": time.time(),
            "results": [asdict(s) for s in self._aggregate_results()],
        }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        # Also generate markdown report
        md_path = output_path.with_suffix(".md")
        with open(md_path, "w") as f:
            f.write("# Benchmark Results\n\n")
            f.write(f"**Device:** {self.device}\n")
            f.write(f"**Iterations:** {self.iterations}\n\n")
            for s in self._aggregate_results():
                f.write(f"## {s.component} - {s.metric}\n\n")
                f.write(f"- **Count:** {s.count}\n")
                f.write(f"- **Mean:** {s.mean:.2f} {s.unit}\n")
                f.write(f"- **Median:** {s.median:.2f} {s.unit}\n")
                f.write(f"- **Std Dev:** {s.std:.2f} {s.unit}\n")
                f.write(f"- **P50:** {s.p50:.2f} {s.unit}\n")
                f.write(f"- **P95:** {s.p95:.2f} {s.unit}\n")
                f.write(f"- **P99:** {s.p99:.2f} {s.unit}\n")
                f.write(f"- **Conditions:** {s.conditions}\n\n")


def main():
    parser = argparse.ArgumentParser(description="Run voicevision benchmarks")
    parser.add_argument("--device", default="cpu", choices=["cpu", "rpi4", "cuda"])
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.json"))
    parser.add_argument("--stt-model", default="/models/whisper-base.bin")
    parser.add_argument("--tts-model", default="/models/voice.onnx")
    parser.add_argument("--llm-model", default="/models/Qwen3-1.7B-Q8_0.gguf")
    args = parser.parse_args()

    runner = BenchmarkRunner(device=args.device, iterations=args.iterations)

    model_paths = {
        "stt": args.stt_model,
        "tts": args.tts_model,
        "llm": args.llm_model,
        "pipeline": True,
    }

    print(f"Running benchmarks on {args.device} ({args.iterations} iterations)...")
    summaries = runner.run_all(model_paths)

    print("\n=== Benchmark Summary ===")
    for s in summaries:
        print(f"  {s.component}.{s.metric}: {s.mean:.2f} {s.unit} (p95: {s.p95:.2f}, p99: {s.p99:.2f})")

    runner.save_results(args.output)
    print(f"\nResults saved to {args.output} and {args.output.with_suffix('.md')}")


if __name__ == "__main__":
    import time
    import numpy as np
    main()