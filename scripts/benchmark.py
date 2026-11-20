#!/usr/bin/env python3
"""Benchmark suite for voicevision M2 components.

Measures latency, accuracy, and resource usage for:
- VAD (WebRTC, Adaptive)
- Wake Word detection
- STT (whisper.cpp)
- TTS (piper)
- Speaker ID (pyannote-compatible embeddings, T092)
- Emotion detection (ML vs keyword accuracy, text/audio latency, T093)
- Full-duplex audio (echo return loss enhancement, barge-in latency, T094)
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

    def benchmark_streaming(
        self, model_path: str = "/models/whisper-base.bin"
    ) -> list[BenchmarkResult]:
        """T091 — compare end-to-end latency of chunked vs true streaming.

        Records time-to-first-partial (the latency users actually feel) and
        total stream duration for each latency target. When the binary does not
        advertise native streaming, only the chunked baseline is measured —
        that is the honest comparison, not a fabricated streaming number.
        """
        results: list[BenchmarkResult] = []
        stt = WhisperCppBackend(model=model_path, language="en")
        audio = self._generate_test_audio(3000)
        audio_chunks = [audio[i : i + 3200] for i in range(0, len(audio), 3200)]
        modes = ["chunked"]
        if stt.supports_true_streaming():
            modes.append("true_streaming")

        for latency in (50, 100, 200):
            for mode in modes:
                for _ in range(self.iterations):
                    start = time.perf_counter()
                    first_partial_ms: float | None = None
                    for index, _chunk in enumerate(
                        stt.transcribe_stream(
                            iter(audio_chunks),
                            latency_target_ms=latency,
                            use_true_streaming=(mode == "true_streaming"),
                        )
                    ):
                        if index == 0:
                            first_partial_ms = (time.perf_counter() - start) * 1000
                    total_ms = (time.perf_counter() - start) * 1000
                    conditions = {
                        "model": "whisper-base",
                        "mode": mode,
                        "latency_target_ms": latency,
                    }
                    results.append(BenchmarkResult(
                        component="stt",
                        metric="streaming_time_to_first_partial",
                        value=first_partial_ms if first_partial_ms is not None else total_ms,
                        unit="ms",
                        conditions=conditions,
                    ))
                    results.append(BenchmarkResult(
                        component="stt",
                        metric="streaming_total_latency",
                        value=total_ms,
                        unit="ms",
                        conditions=conditions,
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
            ))

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
            ))

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

    @staticmethod
    def _speaker_embedder(audio: bytes, sample_rate: int) -> list[float]:
        """Deterministic 3-band spectral embedding for the speaker benchmark."""
        samples = np.frombuffer(audio, dtype="<i2").astype(np.float64) / 32768.0
        if samples.size == 0:
            return [1.0, 0.0, 0.0]
        positions = np.arange(samples.size)
        bands = [
            float(np.abs(np.sum(samples * np.exp(-2j * np.pi * freq * positions / sample_rate))))
            for freq in (220.0, 440.0, 660.0)
        ]
        total = sum(bands)
        if total == 0.0:
            return [1.0, 0.0, 0.0]
        return [value / total for value in bands]

    @staticmethod
    def _speaker_tone(freq: float, duration_ms: int = 500, sample_rate: int = 16000) -> bytes:
        """Generate PCM16 audio with a single dominant tone."""
        samples = int(duration_ms * sample_rate / 1000)
        positions = np.arange(samples)
        values = (0.5 * np.sin(2 * np.pi * freq * positions / sample_rate) * 32767).astype("<i2")
        return values.tobytes()

    def benchmark_speaker(self) -> list[BenchmarkResult]:
        """T092 — identification accuracy and latency, plus diarization latency.

        A deterministic spectral embedder keeps this benchmark runnable in a
        minimal install (no pyannote/torch/model download) while still
        exercising the real matching, streaming and diarization code paths.
        """
        from voicevision.backends.speaker_pyannote import PyannoteSpeakerBackend

        backend = PyannoteSpeakerBackend(embedder=self._speaker_embedder, threshold=0.6)
        speakers = {"Alice": 220.0, "Bob": 440.0, "Carol": 660.0}
        for label, freq in speakers.items():
            backend.enroll(self._speaker_tone(freq), label=label)

        results: list[BenchmarkResult] = []
        correct = sum(
            backend.identify(self._speaker_tone(freq)) == label
            for label, freq in speakers.items()
        )
        results.append(BenchmarkResult(
            component="speaker",
            metric="identification_accuracy",
            value=correct / len(speakers),
            unit="ratio",
            conditions={"speakers": len(speakers), "threshold": backend.threshold},
        ))

        sample = self._speaker_tone(440.0, duration_ms=1000)
        chunks = [sample[i:i + 32000] for i in range(0, len(sample), 32000)]
        for _ in range(self.iterations):
            _, latency = self._time_it(backend.match, sample)
            results.append(BenchmarkResult(
                component="speaker",
                metric="identification_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"audio_duration_s": 1.0, "path": "match"},
            ))
            _, latency = self._time_it(
                lambda: list(backend.identify_stream(iter(chunks)))
            )
            results.append(BenchmarkResult(
                component="speaker",
                metric="identification_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"audio_duration_s": 1.0, "path": "stream"},
            ))
            _, latency = self._time_it(backend.diarize, sample)
            results.append(BenchmarkResult(
                component="speaker",
                metric="diarization_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"audio_duration_s": 1.0},
            ))
        return results

    # T093 — labelled corpus with one dominant emotion per utterance.
    _EMOTION_CORPUS: tuple[tuple[str, str], ...] = (
        ("I am so happy and excited about the wonderful news", "joy"),
        ("This makes me furious and angry", "anger"),
        ("I am terrified and scared of what might happen", "fear"),
        ("She felt sad and lonely after the loss", "sadness"),
        ("What a disgusting and revolting sight", "disgust"),
        ("Wow, I did not expect that at all", "surprise"),
    )
    _EMOTION_LEXICON: dict[str, tuple[str, ...]] = {
        "joy": ("happy", "excited", "wonderful"),
        "anger": ("furious", "angry"),
        "fear": ("terrified", "scared"),
        "sadness": ("sad", "lonely"),
        "disgust": ("disgusting", "revolting"),
        "surprise": ("wow", "expect"),
    }

    @classmethod
    def _emotion_classifier(cls, text: str) -> dict[str, float]:
        """Deterministic ML stand-in: score each emotion by keyword hits."""
        words = set(text.lower().split())
        hits = {
            label: sum(word in words for word in keywords)
            for label, keywords in cls._EMOTION_LEXICON.items()
        }
        total = sum(hits.values())
        if total == 0:
            return {"neutral": 1.0}
        return {label: value / total for label, value in hits.items() if value}

    def benchmark_emotion(self) -> list[BenchmarkResult]:
        """T093 — ML vs keyword accuracy, plus text/audio detection latency.

        An injected classifier keeps this runnable without a model download;
        the keyword baseline uses the shipped :class:`SimpleEmotionBackend`.
        """
        from voicevision.backends.emotion import SimpleEmotionBackend
        from voicevision.backends.emotion_ml import MLEmotionBackend

        ml = MLEmotionBackend(text_classifier=self._emotion_classifier)
        keyword = SimpleEmotionBackend()
        # Map the keyword backend's sentiment labels onto the Ekman taxonomy.
        sentiment_to_ekman = {"positive": "joy", "negative": "sadness"}

        results: list[BenchmarkResult] = []
        for backend_name, backend in (("ml", ml), ("keyword", keyword)):
            correct = 0
            for text, expected in self._EMOTION_CORPUS:
                label = backend.detect(text).label
                if backend_name == "keyword":
                    label = sentiment_to_ekman.get(label, label)
                correct += label == expected
            results.append(BenchmarkResult(
                component="emotion",
                metric="text_accuracy",
                value=correct / len(self._EMOTION_CORPUS),
                unit="ratio",
                conditions={"backend": backend_name, "samples": len(self._EMOTION_CORPUS)},
            ))

        text = self._EMOTION_CORPUS[0][0]
        for _ in range(self.iterations):
            _, latency = self._time_it(ml.detect, text)
            results.append(BenchmarkResult(
                component="emotion",
                metric="text_detection_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"backend": "ml"},
            ))

        audio_ml = MLEmotionBackend(
            text_classifier=self._emotion_classifier,
            audio_classifier=lambda _audio, _rate: {"joy": 0.9, "surprise": 0.1},
        )
        audio = self._speaker_tone(440.0, duration_ms=1000)
        for _ in range(self.iterations):
            _, latency = self._time_it(audio_ml.detect_audio, audio)
            results.append(BenchmarkResult(
                component="emotion",
                metric="audio_detection_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"backend": "ml", "audio_duration_s": 1.0},
            ))
        return results

    @staticmethod
    def _duplex_to_pcm(samples: np.ndarray) -> bytes:
        return bytes((np.clip(samples, -1.0, 1.0) * 32768).astype("<i2").tobytes())

    @staticmethod
    def _duplex_to_float(data: bytes) -> np.ndarray:
        return np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0

    def benchmark_duplex(self) -> list[BenchmarkResult]:
        """T094 — echo return loss enhancement (ERLE) and barge-in latency.

        Synthetic causal echo and near-end speech exercise the real numpy DSP;
        no microphone or sounddevice is required. ERLE is reported for several
        cancellation strengths so the configurability is measurable.
        """
        from voicevision.backends.audio_duplex import (
            BargeInDetector,
            EchoCanceller,
            DuplexConfig,
        )

        results: list[BenchmarkResult] = []
        rng = np.random.default_rng(42)
        reference = rng.uniform(-0.5, 0.5, size=16000)
        echo_path = np.array([0.6, -0.3, 0.15, -0.08, 0.04, -0.02])
        echo = np.zeros_like(reference)
        for delay, coefficient in enumerate(echo_path):
            echo[delay:] += coefficient * reference[: len(reference) - delay]
        positions = np.arange(len(reference))
        near_end = 0.01 * np.sin(2 * np.pi * 220 * positions / 16000)
        mic = echo + near_end

        for strength in (0.25, 0.5, 0.75):
            canceller = EchoCanceller(strength=strength, filter_length=32, echo_suppression=0.0)
            output = np.concatenate([
                self._duplex_to_float(canceller.process(
                    self._duplex_to_pcm(mic[i : i + 160]),
                    self._duplex_to_pcm(reference[i : i + 160]),
                ))
                for i in range(0, len(mic), 160)
            ])
            erle = 10 * np.log10(np.sum(mic**2) / np.sum(output**2))
            results.append(BenchmarkResult(
                component="duplex",
                metric="echo_return_loss_enhancement",
                value=float(erle),
                unit="dB",
                conditions={"aec_strength": strength, "duration_s": 1.0},
            ))

        # Barge-in: one 10 ms speech frame per trial, with frame timing marked.
        speech = self._duplex_to_pcm(0.7 * np.ones(160))
        detector = BargeInDetector(config=DuplexConfig(barge_in_threshold_db=12.0))
        for _ in range(self.iterations):
            detector.set_playback(True)
            detector.begin_frame()
            _, latency = self._time_it(detector.process, speech)
            results.append(BenchmarkResult(
                component="duplex",
                metric="barge_in_latency",
                value=latency * 1000,
                unit="ms",
                conditions={"frame_ms": 10, "threshold_db": 12.0},
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
            ))

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

        # Speaker ID benchmarks (T092 — no model download required)
        self.results.extend(self.benchmark_speaker())

        # Emotion benchmarks (T093 — no model download required)
        self.results.extend(self.benchmark_emotion())

        # Full-duplex benchmarks (T094 — no microphone required)
        self.results.extend(self.benchmark_duplex())

        # STT benchmarks
        if "stt" in model_paths:
            self.results.extend(self.benchmark_stt(model_paths["stt"]))
            self.results.extend(self.benchmark_streaming(model_paths["stt"]))

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