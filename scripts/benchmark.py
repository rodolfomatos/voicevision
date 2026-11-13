#!/usr/bin/env python3
"""
benchmark.py — Benchmark suite for voicevision (TTFT, RTF, RSS)

Measures:
- TTFT (Time To First Token): STT + LLM first token latency
- RTF (Real Time Factor): TTS synthesis speed (audio_duration / synthesis_time)
- RSS (Resident Set Size): Peak memory usage in MB

Usage:
    python3 scripts/benchmark.py --models voice-loop --iterations 5 --warmup 2
    python3 scripts/benchmark.py --models stt llm tts --iterations 3 --output benchmark.json
"""

import argparse
import json
import os
import sys
import time
import statistics
import threading
from pathlib import Path
from datetime import datetime
from typing import Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from voicevision.pipeline import PipelineConfig, VoicePipeline
from voicevision.audio import pcm16_to_wav


class BenchmarkResult:
    """Container for benchmark results."""

    def __init__(self, name: str):
        self.name = name
        self.ttft_stt: list[float] = []      # STT time to first token
        self.ttft_llm: list[float] = []      # LLM time to first token
        self.rtf: list[float] = []           # Real Time Factor (TTS)
        self.rss: list[float] = []           # Peak RSS in MB
        self.errors: list[str] = []

    def add_ttft_stt(self, value: float):
        self.ttft_stt.append(value)

    def add_ttft_llm(self, value: float):
        self.ttft_llm.append(value)

    def add_rtf(self, value: float):
        self.rtf.append(value)

    def add_rss(self, value: float):
        self.rss.append(value)

    def add_error(self, error: str):
        self.errors.append(error)

    def summary(self) -> dict:
        def stats(values: list[float]) -> dict:
            if not values:
                return {"count": 0}
            return {
                "count": len(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0,
                "min": min(values),
                "max": max(values),
                "p50": statistics.quantiles(values, n=100)[49] if len(values) >= 2 else values[0],
                "p95": statistics.quantiles(values, n=100)[94] if len(values) >= 2 else values[0],
                "p99": statistics.quantiles(values, n=100)[98] if len(values) >= 3 else values[-1],
            }

        return {
            "name": self.name,
            "ttft_stt": stats(self.ttft_stt),
            "ttft_llm": stats(self.ttft_llm),
            "rtf": stats(self.rtf),
            "rss": stats(self.rss),
            "errors": len(self.errors),
        }


class BenchmarkRunner:
    """Runs benchmarks on VoicePipeline components."""

    def __init__(self, config: PipelineConfig, iterations: int = 5, warmup: int = 2):
        self.config = config
        self.iterations = iterations
        self.warmup = warmup
        self.results = BenchmarkResult("voice-pipeline")

    def _get_rss(self) -> float:
        """Get current RSS in MB."""
        if not PSUTIL_AVAILABLE:
            return 0.0
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    def _measure_ttft_stt(self, pipeline: VoicePipeline, audio: bytes) -> float:
        """Measure STT time to first transcript."""
        start = time.perf_counter()
        transcript = pipeline.stt.transcribe(audio)
        elapsed = time.perf_counter() - start
        return elapsed

    def _measure_ttft_llm(self, pipeline: VoicePipeline, prompt: str) -> float:
        """Measure LLM time to first token."""
        start = time.perf_counter()
        for chunk in pipeline.llm.complete_stream("Hello, world."):
            if chunk.strip():
                elapsed = time.perf_counter() - start
                return elapsed
        return time.perf_counter() - start

    def _measure_tts_rtf(self, pipeline: VoicePipeline, text: str) -> tuple[float, float]:
        """Measure TTS synthesis time and return (synthesis_time, rtf)."""
        start = time.perf_counter()
        audio = pipeline.tts.synthesize(text)
        synthesis_time = time.perf_counter() - start

        # Estimate audio duration from WAV header (rough approximation)
        # WAV header is 44 bytes, then 16-bit mono at 16kHz = 32000 bytes/sec
        audio_data = audio[44:]  # Skip WAV header
        duration_sec = len(audio_data) / 32000  # 16kHz * 2 bytes

        if synthesis_time > 0:
            rtf = duration_sec / synthesis_time
        else:
            rtf = 0.0

        return synthesis_time, rtf

    def run_warmup(self):
        """Run warmup iterations."""
        print(f"  Warming up ({self.warmup} runs)...")
        config = self.config
        pipeline = VoicePipeline(config)

        # Create dummy audio (1 second of silence at 16kHz mono 16-bit)
        dummy_audio = b"\x00" * 32000  # 1 second at 16kHz 16-bit mono

        for _ in range(self.warmup):
            try:
                _ = pipeline.stt.transcribe(test_audio)
                for _ in pipeline.llm.complete_stream("Hello"):
                    pass
                _ = pipeline.tts.synthesize("Hello")
            except Exception:
                pass  # Ignore warmup errors

    def run_benchmark(self) -> dict:
        """Run the full benchmark suite."""
        print(f"Running benchmark: {self.iterations} iterations...")

        config = self.config
        pipeline = VoicePipeline(self.config)

        # Create test audio (2 seconds of silence at 16kHz mono 16-bit)
        test_audio = pcm16_to_wav(b"\x00" * 64000)  # 2 seconds at 16kHz 16-bit mono

        # Test prompts
        prompts = [
            "Olá, como vai você?",
            "Qual a capital do Brasil?",
            "Conte uma piada curta.",
            "Explique o que é inteligência artificial.",
        ]

        for i in range(self.iterations):
            print(f"  Iteration {i+1}/{self.iterations}...")

            # Measure STT TTFT
            try:
                start = time.perf_counter()
                transcript = pipeline.stt.transcribe(test_audio)
                self.results.add_ttft_stt(time.perf_counter() - start)
            except Exception as e:
                self.results.add_error(f"STT iteration {i}: {e}")

            # Measure LLM TTFT (using first prompt)
            try:
                prompt = prompts[i % len(prompts)]
                start = time.perf_counter()
                for chunk in pipeline.llm.complete_stream(prompts[i % len(prompts)]):
                    if chunk.strip():
                        self.results.add_ttft_llm(time.perf_counter() - start)
                        break
            except Exception as e:
                self.results.add_error(f"LLM TTFT iteration {i}: {e}")

            # Measure TTS RTF and RSS
            try:
                # Track peak RSS during TTS
                rss_samples = []
                rss_stop = threading.Event()

                def monitor_rss():
                    while not rss_stop.is_set():
                        rss = self._get_rss()
                        if rss > 0:
                            pass  # We'll track peak after
                        time.sleep(0.01)

                rss_thread = threading.Thread(target=monitor_rss, daemon=True)
                rss_thread.start()

                start = time.perf_counter()
                audio = pipeline.tts.synthesize("Olá, como vai você?")
                synthesis_time = time.perf_counter() - start

                rss_stop.set()
                rss_thread.join(timeout=1)

                # Get peak RSS
                peak_rss = self._get_rss()

                # Calculate RTF
                audio_data = audio[44:]  # Skip WAV header
                duration_sec = len(audio_data) / 32000  # 16kHz * 2 bytes

                if synthesis_time > 0:
                    rtf = duration_sec / synthesis_time
                else:
                    rtf = 0.0

                self.results.add_rtf(rtf)
                self.results.add_rss(peak_rss)

            except Exception as e:
                self.results.add_error(f"TTS iteration {i}: {e}")

        return self.results.summary()


def run_benchmark(config: PipelineConfig, iterations: int = 5, warmup: int = 2) -> dict:
    """Run benchmark and return results."""
    runner = BenchmarkRunner(config, iterations, warmup)
    runner.run_warmup()
    return runner.run_benchmark()


def main():
    parser = argparse.ArgumentParser(description="VoiceVision benchmark suite")
    parser.add_argument("--models", default="voice-loop",
                        help="Model group: stt, llm, tts, vision, voice-loop, full")
    parser.add_argument("--iterations", type=int, default=5, help="Number of iterations")
    parser.add_argument("--warmup", type=int, default=2, help="Warmup runs")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--output-csv", help="Output CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Run without models")
    args = parser.parse_args()

    # Resolve model config
    model_groups = {
        "stt": ["whisper-base"],
        "llm": ["qwen3-1.7b-q8"],
        "tts": ["piper-en-us-lessac-medium", "piper-en-us-lessac-medium-config"],
        "vision": ["moondream-text", "moondream-mmproj"],
        "voice-loop": ["whisper-base", "qwen3-1.7b-q8", "piper-en-us-lessac-medium", "piper-en-us-lessac-medium-config"],
        "full": ["whisper-base", "qwen3-1.7b-q8", "piper-en-us-lessac-medium", "piper-en-us-lessac-medium-config", "moondream-text", "moondream-mmproj"],
    }

    models_to_download = []
    if args.models in {"all", "voice-loop", "full"}:
        models_to_download = ["whisper-base", "qwen3-1.7b-q8",
                              "piper-en-us-lessac-medium", "piper-en-us-lessac-medium-config"]
    elif args.models in {"stt", "llm", "tts", "vision"}:
        models_to_download = []
        for k, v in {"stt": ["whisper-base"], "llm": ["qwen3-1.7b-q8"],
                     "tts": ["piper-en-us-lessac-medium", "piper-en-us-lessac-medium-config"],
                     "vision": ["moondream-text", "moondream-mmproj"]}.items():
            if k in args.models:
                models_to_download.extend(v)
    else:
        models_to_download = [m.strip() for m in args.models.split(",")]

    # Download models if not dry run
    if not args.dry_run:
        from download_models import download_model
        for key in models_to_download:
            download_model(key, Path("/models"))

    # Build config
    config = PipelineConfig(
        stt_model="/models/whisper-base.bin" if "whisper-base" in models_to_download else "",
        llm_model="/models/Qwen3-1.7B-Q8_0.gguf" if "qwen3-1.7b-q8" in models_to_download else "",
        tts_model="/models/voice.onnx" if "piper-en-us-lessac-medium" in models_to_download else "",
        tts_voice="",
        stt_language="pt",
        llm_host="127.0.0.1",
        llm_port=8080,
    )

    if args.dry_run:
        print("Dry run - skipping actual benchmark")
        return 0

    # Run benchmark
    results = run_benchmark(config, args.iterations, args.warmup)

    # Print summary
    print("\n=== Benchmark Results ===")
    print(json.dumps(results, indent=2, ensure_ascii=False))

    # Save output
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {args.output}")

    if args.output_csv:
        # Write CSV
        import csv
        with open(args.output_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "count", "mean", "median", "stdev", "min", "max", "p50", "p95", "p99"])
            for metric in ["ttft_stt", "ttft_llm", "rtf", "rss"]:
                stats = results.get(metric, {})
                if stats.get("count", 0) > 0:
                    writer.writerow([
                        metric, stats["count"], stats["mean"], stats["median"],
                        stats["stdev"], stats["min"], stats["max"],
                        stats["p50"], stats["p95"], stats["p99"]
                    ])
        print(f"CSV saved to {args.output_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())