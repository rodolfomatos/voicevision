"""Tests for VoicePipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from voicevision.pipeline import PipelineConfig, VoicePipeline


# Mock the backends to avoid real subprocess calls
@pytest.fixture
def mock_backends():
    """Mock all backends for pipeline testing."""
    with patch("voicevision.pipeline.WebrtcVadBackend") as mock_vad, \
         patch("voicevision.pipeline.WhisperCppBackend") as mock_stt, \
         patch("voicevision.pipeline.LlamaCppBackend") as mock_llm, \
         patch("voicevision.pipeline.PiperBackend") as mock_tts:

        # Setup VAD mock
        vad_instance = MagicMock()
        mock_vad.return_value = vad_instance

        # Setup STT mock
        stt_instance = MagicMock()
        mock_stt.return_value = stt_instance

        # Setup LLM mock
        llm_instance = MagicMock()
        mock_llm.return_value = llm_instance

        # Setup TTS mock
        tts_instance = MagicMock()
        mock_tts.return_value = tts_instance

        yield {
            "vad": mock_vad,
            "vad_instance": vad_instance,
            "stt": mock_stt,
            "stt_instance": stt_instance,
            "llm": mock_llm,
            "llm_instance": llm_instance,
            "tts": mock_tts,
            "tts_instance": tts_instance,
        }


class TestPipelineConfig:
    def test_defaults(self) -> None:
        config = PipelineConfig()
        assert config.vad_aggressiveness == 2
        assert config.vad_sample_rate == 16000
        assert config.vad_silence_ms == 500
        assert config.vad_max_utterance_ms == 30000


class TestPipelineInitialization:
    def test_creates_with_config(self) -> None:
        config = PipelineConfig(
            stt_model="/models/whisper.bin",
            llm_model="/models/llama.gguf",
            tts_model="/models/piper.onnx",
        )
        pipeline = VoicePipeline(config)
        assert pipeline.config == config

    def test_lazy_backend_initialization(self, mock_backends) -> None:
        """Backends are not created until accessed."""
        config = PipelineConfig(
            stt_model="/models/whisper.bin",
            llm_model="/models/llama.gguf",
            tts_model="/models/piper.onnx",
        )
        pipeline = VoicePipeline(config)

        # Backends should not be created yet
        assert pipeline._vad is None
        assert pipeline._stt is None
        assert pipeline._llm is None
        assert pipeline._tts is None

        # Accessing property creates backend
        _ = pipeline.vad
        assert pipeline._vad is not None


class TestPipelineProcess:
    def test_empty_audio_returns_empty(self, mock_backends) -> None:
        """Empty audio returns empty bytes."""
        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        pipeline = VoicePipeline(config)

        result = pipeline.process(b"")
        assert result == b""

    def test_silence_returns_empty(self, mock_backends) -> None:
        """All-silence audio returns empty bytes."""
        mock_backends["vad_instance"].segment.return_value = []

        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        pipeline = VoicePipeline(config)

        result = pipeline.process(b"silence" * 100)
        assert result == b""

    def test_single_utterance_processed(self, mock_backends) -> None:
        """Single utterance goes through full pipeline."""
        mock_backends["vad_instance"].segment.return_value = [(0, 960)]
        mock_backends["stt_instance"].transcribe.return_value = "hello"
        mock_backends["llm_instance"].complete.return_value = type("Completion", (), {"content": "hi there", "thinking": ""})()
        mock_backends["tts_instance"].synthesize.return_value = b"RIFF....WAVE"

        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        pipeline = VoicePipeline(config)

        result = pipeline.process(b"x" * 960)
        assert result == b"RIFF....WAVE"

        # Verify call chain
        mock_backends["vad_instance"].segment.assert_called_once()
        mock_backends["stt_instance"].transcribe.assert_called_once()
        mock_backends["llm_instance"].complete.assert_called_once()
        mock_backends["tts_instance"].synthesize.assert_called_once_with("hi there")

    def test_multiple_utterances_concatenated(self, mock_backends) -> None:
        """Multiple utterances produce concatenated output."""
        mock_backends["vad_instance"].segment.return_value = [(0, 960), (960, 1920)]
        mock_backends["stt_instance"].transcribe.side_effect = ["hello", "world"]
        mock_backends["llm_instance"].complete.side_effect = [
            type("Completion", (), {"content": "hi", "thinking": ""})(),
            type("Completion", (), {"content": "there", "thinking": ""})(),
        ]
        mock_backends["tts_instance"].synthesize.side_effect = [b"wav1", b"wav2"]

        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        pipeline = VoicePipeline(config)

        result = pipeline.process(b"x" * 1920)
        assert result == b"wav1wav2"
        assert mock_backends["tts_instance"].synthesize.call_count == 2

    def test_empty_transcript_skipped(self, mock_backends) -> None:
        """Empty transcript skips LLM and TTS."""
        mock_backends["vad_instance"].segment.return_value = [(0, 960)]
        mock_backends["stt_instance"].transcribe.return_value = ""  # Empty transcript

        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        pipeline = VoicePipeline(config)

        result = pipeline.process(b"x" * 960)
        assert result == b""
        mock_backends["llm_instance"].complete.assert_not_called()
        mock_backends["tts_instance"].synthesize.assert_not_called()

    def test_thinking_filter_strips_reasoning(self, mock_backends) -> None:
        """Thinking filter strips qwen3 reasoning traces."""
        mock_backends["vad_instance"].segment.return_value = [(0, 960)]
        mock_backends["stt_instance"].transcribe.return_value = "hello"
        # Content includes qwen3-style thinking markers
        mock_backends["llm_instance"].complete.return_value = type(
            "Completion", (), {"content": "thinking...hi", "thinking": "thinking..."}
        )()
        mock_backends["tts_instance"].synthesize.return_value = b"wav"

        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
            enable_thinking_filter=True,
        )
        pipeline = VoicePipeline(config)

        pipeline.process(b"x" * 960)

        # TTS should receive filtered text (thinking stripped)
        mock_backends["tts_instance"].synthesize.assert_called_with("hi")

    def test_thinking_filter_disabled(self, mock_backends) -> None:
        """When disabled, thinking trace is not filtered."""
        mock_backends["vad_instance"].segment.return_value = [(0, 960)]
        mock_backends["stt_instance"].transcribe.return_value = "hello"
        mock_backends["llm_instance"].complete.return_value = type(
            "Completion", (), {"content": "thinking...hi", "thinking": "thinking..."}
        )()
        mock_backends["tts_instance"].synthesize.return_value = b"wav"

        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
            enable_thinking_filter=False,
        )
        pipeline = VoicePipeline(config)

        pipeline.process(b"x" * 960)

        # TTS should receive unfiltered text
        mock_backends["tts_instance"].synthesize.assert_called_with("thinking...hi")

    def test_context_manager_closes_backends(self, mock_backends) -> None:
        """Context manager properly closes all backends."""
        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        with VoicePipeline(config) as pipeline:
            _ = pipeline.vad  # Initialize
            _ = pipeline.stt
            _ = pipeline.llm
            _ = pipeline.tts

        # All backends should have close() called
        mock_backends["vad_instance"].close.assert_called_once()
        mock_backends["stt_instance"].close.assert_called_once()
        mock_backends["llm_instance"].close.assert_called_once()
        mock_backends["tts_instance"].close.assert_called_once()

    def test_explicit_close_calls_backend_close(self, mock_backends) -> None:
        """Explicit close() calls all backend close methods."""
        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        pipeline = VoicePipeline(config)
        _ = pipeline.vad
        _ = pipeline.stt
        _ = pipeline.llm
        _ = pipeline.tts

        pipeline.close()

        mock_backends["vad_instance"].close.assert_called_once()
        mock_backends["stt_instance"].close.assert_called_once()
        mock_backends["llm_instance"].close.assert_called_once()
        mock_backends["tts_instance"].close.assert_called_once()

    def test_close_idempotent(self, mock_backends) -> None:
        """Multiple close() calls are safe."""
        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        pipeline = VoicePipeline(config)
        _ = pipeline.vad
        pipeline.close()
        pipeline.close()
        pipeline.close()

        assert mock_backends["vad_instance"].close.call_count == 3


class TestPipelineStream:
    def test_stream_processes_chunks(self, mock_backends) -> None:
        """Stream processes chunks and yields speech."""
        # side_effect with 3 values: first call returns utterance, second empty, third empty
        # (loop iteration 1, loop iteration 2, final buffer check)
        mock_backends["vad_instance"].segment.side_effect = [
            [(0, 960)],  # First chunk has utterance
            [],        # Second chunk has none
            [],        # Final buffer check
        ]
        mock_backends["stt_instance"].transcribe.return_value = "hello"
        mock_backends["llm_instance"].complete.return_value = type(
            "Completion", (), {"content": "hi", "thinking": ""}
        )()
        mock_backends["tts_instance"].synthesize.return_value = b"wav"

        config = PipelineConfig(
            stt_model="/m.bin",
            llm_model="/m.gguf",
            tts_model="/m.onnx",
        )
        pipeline = VoicePipeline(config)

        def chunk_iter():
            yield b"x" * 480
            yield b"x" * 480

        results = list(pipeline.process_stream(chunk_iter()))

        assert len(results) == 1
        assert results[0] == b"wav"


class TestPipelineConfigValidation:
    def test_missing_stt_model_raises(self) -> None:
        config = PipelineConfig(llm_model="/m.gguf", tts_model="/m.onnx")
        pipeline = VoicePipeline(config)
        with pytest.raises(ValueError, match="stt_model must be configured"):
            _ = pipeline.stt

    def test_missing_llm_model_raises(self) -> None:
        config = PipelineConfig(stt_model="/m.bin", tts_model="/m.onnx")
        pipeline = VoicePipeline(config)
        with pytest.raises(ValueError, match="llm_model must be configured"):
            _ = pipeline.llm

    def test_missing_tts_model_raises(self) -> None:
        config = PipelineConfig(stt_model="/m.bin", llm_model="/m.gguf")
        pipeline = VoicePipeline(config)
        with pytest.raises(ValueError, match="tts_model must be configured"):
            _ = pipeline.tts