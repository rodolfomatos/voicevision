# M2 Benchmark Baseline Report

*Generated on: {{DATE}}*
*Device: {{DEVICE}}*
*Iterations: {{ITERATIONS}}*

---

## Summary

This document presents the baseline performance metrics for voicevision M2 components.
All measurements are taken on {{DEVICE}} with {{ITERATIONS}} iterations per test.

---

## VAD (Voice Activity Detection)

### WebRTC VAD

| Metric | Mean | Median | Std Dev | P50 | P95 | P99 | Unit |
|--------|------|--------|---------|-----|-----|-----|------|
| Speech Detection Latency | {{VAD_WEBRTC_SPEECH_LATENCY_MEAN}} | {{VAD_WEBRTC_SPEECH_LATENCY_MEDIAN}} | {{VAD_WEBRTC_SPEECH_LATENCY_STD}} | {{VAD_WEBRTC_SPEECH_LATENCY_P50}} | {{VAD_WEBRTC_SPEECH_LATENCY_P95}} | {{VAD_WEBRTC_SPEECH_LATENCY_P99}} | ms |
| Silence Detection Latency | {{VAD_WEBRTC_SILENCE_LATENCY_MEAN}} | {{VAD_WEBRTC_SILENCE_LATENCY_MEDIAN}} | {{VAD_WEBRTC_SILENCE_LATENCY_STD}} | {{VAD_WEBRTC_SILENCE_LATENCY_P50}} | {{VAD_WEBRTC_SILENCE_LATENCY_P95}} | {{VAD_WEBRTC_SILENCE_LATENCY_P99}} | ms |

### Adaptive VAD

| Metric | Mean | Median | Std Dev | P50 | P95 | P99 | Unit |
|--------|------|--------|---------|-----|-----|-----|------|
| Speech Detection Latency | {{VAD_ADAPTIVE_SPEECH_LATENCY_MEAN}} | {{VAD_ADAPTIVE_SPEECH_LATENCY_MEDIAN}} | {{VAD_ADAPTIVE_SPEECH_LATENCY_STD}} | {{VAD_ADAPTIVE_SPEECH_LATENCY_P50}} | {{VAD_ADAPTIVE_SPEECH_LATENCY_P95}} | {{VAD_ADAPTIVE_SPEECH_LATENCY_P99}} | ms |
| Silence Detection Latency | {{VAD_ADAPTIVE_SILENCE_LATENCY_MEAN}} | {{VAD_ADAPTIVE_SILENCE_LATENCY_MEDIAN}} | {{VAD_ADAPTIVE_SILENCE_LATENCY_STD}} | {{VAD_ADAPTIVE_SILENCE_LATENCY_P50}} | {{VAD_ADAPTIVE_SILENCE_LATENCY_P95}} | {{VAD_ADAPTIVE_SILENCE_LATENCY_P99}} | ms |

---

## Wake Word Detection

| Metric | Mean | Median | Std Dev | P50 | P95 | P99 | Unit |
|--------|------|--------|---------|-----|-----|-----|------|
| Detection Latency | {{WAKE_WORD_LATENCY_MEAN}} | {{WAKE_WORD_LATENCY_MEDIAN}} | {{WAKE_WORD_LATENCY_STD}} | {{WAKE_WORD_LATENCY_P50}} | {{WAKE_WORD_LATENCY_P95}} | {{WAKE_WORD_LATENCY_P99}} | ms |
| False Positive Rate | {{WAKE_WORD_FPR_MEAN}} | - | - | - | - | - | % |
| False Negative Rate | {{WAKE_WORD_FNR_MEAN}} | - | - | - | - | - | % |

---

## STT (Speech-to-Text)

### whisper.cpp (whisper-base)

| Metric | Mean | Median | Std Dev | P50 | P95 | P99 | Unit |
|--------|------|--------|---------|-----|-----|-----|------|
| Full Transcription Latency (3s audio) | {{STT_FULL_LATENCY_MEAN}} | {{STT_FULL_LATENCY_MEDIAN}} | {{STT_FULL_LATENCY_STD}} | {{STT_FULL_LATENCY_P50}} | {{STT_FULL_LATENCY_P95}} | {{STT_FULL_LATENCY_P99}} | ms |
| Streaming First Chunk Latency | {{STT_STREAMING_FIRST_LATENCY_MEAN}} | {{STT_STREAMING_FIRST_LATENCY_MEDIAN}} | {{STT_STREAMING_FIRST_LATENCY_STD}} | {{STT_STREAMING_FIRST_LATENCY_P50}} | {{STT_STREAMING_FIRST_LATENCY_P95}} | {{STT_STREAMING_FIRST_LATENCY_P99}} | ms |
| Word Error Rate (clean) | {{STT_WER_CLEAN_MEAN}} | - | - | - | - | - | % |
| Word Error Rate (noisy) | {{STT_WER_NOISY_MEAN}} | - | - | - | - | - | % |

---

## TTS (Text-to-Speech)

### Piper (en_US-lessac-medium)

| Metric | Mean | Median | Std Dev | P50 | P95 | P99 | Unit |
|--------|------|--------|---------|-----|-----|-----|------|
| Synthesis Latency | {{TTS_SYNTHESIS_LATENCY_MEAN}} | {{TTS_SYNTHESIS_LATENCY_MEDIAN}} | {{TTS_SYNTHESIS_LATENCY_STD}} | {{TTS_SYNTHESIS_LATENCY_P50}} | {{TTS_SYNTHESIS_LATENCY_P95}} | {{TTS_SYNTHESIS_LATENCY_P99}} | ms |
| Real-Time Factor (RTF) | {{TTS_RTF_MEAN}} | {{TTS_RTF_MEDIAN}} | {{TTS_RTF_STD}} | {{TTS_RTF_P50}} | {{TTS_RTF_P95}} | {{TTS_RTF_P99}} | ratio |
| Streaming First Chunk Latency | {{TTS_STREAMING_FIRST_LATENCY_MEAN}} | {{TTS_STREAMING_FIRST_LATENCY_MEDIAN}} | {{TTS_STREAMING_FIRST_LATENCY_STD}} | {{TTS_STREAMING_FIRST_LATENCY_P50}} | {{TTS_STREAMING_FIRST_LATENCY_P95}} | {{TTS_STREAMING_FIRST_LATENCY_P99}} | ms |

---

## Full Pipeline (VAD → STT → LLM → TTS)

| Metric | Mean | Median | Std Dev | P50 | P95 | P99 | Unit |
|--------|------|--------|---------|-----|-----|-----|------|
| Full Pipeline Latency (3s audio) | {{PIPELINE_FULL_LATENCY_MEAN}} | {{PIPELINE_FULL_LATENCY_MEDIAN}} | {{PIPELINE_FULL_LATENCY_STD}} | {{PIPELINE_FULL_LATENCY_P50}} | {{PIPELINE_FULL_LATENCY_P95}} | {{PIPELINE_FULL_LATENCY_P99}} | ms |
| Time to First Token (TTFT) | {{PIPELINE_TTFT_MEAN}} | {{PIPELINE_TTFT_MEDIAN}} | {{PIPELINE_TTFT_STD}} | {{PIPELINE_TTFT_P50}} | {{PIPELINE_TTFT_P95}} | {{PIPELINE_TTFT_P99}} | ms |
| Interruption Latency (barge-in) | {{PIPELINE_INTERRUPTION_MEAN}} | {{PIPELINE_INTERRUPTION_MEDIAN}} | {{PIPELINE_INTERRUPTION_STD}} | {{PIPELINE_INTERRUPTION_P50}} | {{PIPELINE_INTERRUPTION_P95}} | {{PIPELINE_INTERRUPTION_P99}} | ms |

---

## Hardware & Environment

| Parameter | Value |
|-----------|-------|
| Device | {{DEVICE}} |
| CPU | {{CPU_INFO}} |
| Memory | {{MEMORY_INFO}} |
| OS | {{OS_INFO}} |
| Python | {{PYTHON_VERSION}} |
| voicevision version | {{VOICEVISION_VERSION}} |

---

## Test Conditions

| Parameter | Value |
|-----------|-------|
| Iterations per test | {{ITERATIONS}} |
| Audio sample rate | 16 kHz |
| Audio format | 16-bit PCM mono |
| Test audio duration | 3 seconds |
| Noise conditions | Clean / CHiME noise (0dB, 10dB SNR) |
| Languages tested | en, pt |

---

## Notes

- All latencies measured with `time.perf_counter()` for high precision
- Percentiles computed using `numpy.percentile` with linear interpolation
- Outliers beyond 3 standard deviations excluded from mean/std calculations
- Results are reproducible with fixed random seed for synthetic audio generation

---

## Version Information

| Component | Version |
|-----------|---------|
| voicevision | {{VOICEVISION_VERSION}} |
| whisper.cpp | {{WHISPER_CPP_VERSION}} |
| piper | {{PIPER_VERSION}} |
| webrtcvad | {{WEBRTCVAD_VERSION}} |
| Python | {{PYTHON_VERSION}} |

---

*Report generated by `scripts/benchmark.py` on {{DATE}}*