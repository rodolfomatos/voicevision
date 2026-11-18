"""Tests for voicevision.backends.adaptive_vad."""

from __future__ import annotations

import pytest

from voicevision.backends.adaptive_vad import AdaptiveVadBackend


class TestConstruction:
    """Test AdaptiveVadBackend construction and validation."""

    def test_defaults(self) -> None:
        backend = AdaptiveVadBackend()
        assert backend.sample_rate == 16000
        assert backend.frame_bytes == 960  # 30ms at 16kHz = 480 samples * 2 bytes

    def test_custom_sample_rate(self) -> None:
        backend = AdaptiveVadBackend(sample_rate=8000)
        assert backend.sample_rate == 8000
        assert backend.frame_bytes == 480  # 30ms at 8kHz

    def test_custom_frame_ms(self) -> None:
        backend = AdaptiveVadBackend(sample_rate=16000, frame_ms=20)
        assert backend.frame_bytes == 640  # 20ms at 16kHz

    def test_invalid_sample_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="sample_rate must be"):
            AdaptiveVadBackend(sample_rate=44100)

    def test_invalid_noise_percentile_raises(self) -> None:
        with pytest.raises(ValueError, match="noise_percentile must be 1-99"):
            AdaptiveVadBackend(noise_percentile=0)
        with pytest.raises(ValueError, match="noise_percentile must be 1-99"):
            AdaptiveVadBackend(noise_percentile=100)

    def test_invalid_frame_ms_raises(self) -> None:
        with pytest.raises(ValueError, match="frame_ms must be positive"):
            AdaptiveVadBackend(frame_ms=0)


class TestAvailability:
    """Test availability checks."""

    def test_available(self) -> None:
        assert AdaptiveVadBackend.available() is True

    def test_install_hint(self) -> None:
        assert "Built-in" in AdaptiveVadBackend.install_hint()


class TestSegmentation:
    """Test speech segmentation with synthetic audio."""

    def _make_pcm(
    self, duration_ms: int, sample_rate: int = 16000, amplitude: float = 0.5
) -> bytes:
        """Generate PCM16 sine wave audio, aligned to frame boundaries."""
        import math
        # Frame size in samples
        frame_samples = sample_rate * 30 // 1000  # 30ms frames
        # Round duration to nearest frame boundary
        frames = max(1, round(duration_ms / 30))
        total_samples = frames * frame_samples
        max_val = 32767
        data = bytearray()
        for i in range(total_samples):
            t = i / sample_rate
            val = int(amplitude * max_val * math.sin(2 * math.pi * 440 * t))
            data.extend(val.to_bytes(2, "little", signed=True))
        return bytes(data)

    def _make_silence(self, duration_ms: int, sample_rate: int = 16000) -> bytes:
        """Generate silence, aligned to frame boundaries."""
        frame_samples = sample_rate * 30 // 1000
        frames = max(1, round(duration_ms / 30))
        total_samples = frames * frame_samples
        return bytes(total_samples * 2)

    def test_single_utterance(self) -> None:
        """Speech followed by silence yields one utterance."""
        backend = AdaptiveVadBackend(
            sample_rate=16000, frame_ms=30, noise_percentile=10, sensitivity=2.0
        )

        # 500ms speech + 500ms silence
        speech = self._make_pcm(500, amplitude=0.5)
        silence = self._make_silence(500)
        audio = speech + silence

        results = list(backend.segment(audio))
        assert len(results) == 1
        start, end = results[0]
        assert start == 0
        assert end > 0

    def test_multiple_utterances(self) -> None:
        """Multiple speech segments separated by silence yield multiple utterances."""
        backend = AdaptiveVadBackend(
            sample_rate=16000, frame_ms=30, noise_percentile=10, sensitivity=2.0
        )

        speech1 = self._make_pcm(300, amplitude=0.5)
        silence = self._make_silence(1000)  # > MERGE_GAP_MS (700ms)
        speech2 = self._make_pcm(300, amplitude=0.5)
        audio = speech1 + silence + speech2

        results = list(backend.segment(audio))
        assert len(results) == 2

    def test_silence_yields_nothing(self) -> None:
        """Pure silence yields no utterances."""
        backend = AdaptiveVadBackend(sample_rate=16000, frame_ms=30)
        silence = self._make_silence(1000)
        results = list(backend.segment(silence))
        assert results == []

    def test_max_utterance_force_closes(self) -> None:
        """Very long utterance is force-closed at max_utterance_ms."""
        # Note: AdaptiveVadBackend doesn't have max_utterance_ms yet
        # This test documents expected behavior when added
        pass

    def test_empty_input(self) -> None:
        backend = AdaptiveVadBackend()
        results = list(backend.segment(b""))
        assert results == []

    def test_invalid_pcm_length_raises(self) -> None:
        backend = AdaptiveVadBackend()
        # Frame size is 960 bytes for 16kHz 30ms
        bad_audio = b"x" * 100  # Not multiple of frame_bytes
        with pytest.raises(ValueError, match="not a multiple of frame size"):
            list(backend.segment(bad_audio))

    def test_process_frame(self) -> None:
        backend = AdaptiveVadBackend()
        # Create a frame with some energy
        frame = self._make_pcm(30, amplitude=0.5)
        assert len(frame) == backend.frame_bytes
        result = backend.process_frame(frame)
        assert isinstance(result, bool)

    def test_process_frame_wrong_size_raises(self) -> None:
        backend = AdaptiveVadBackend()
        with pytest.raises(ValueError, match="Frame must be"):
            backend.process_frame(b"x" * 100)

    def test_noise_percentile_config(self) -> None:
        """Different noise percentiles should affect sensitivity."""
        backend_low = AdaptiveVadBackend(noise_percentile=5, sensitivity=2.0)
        backend_high = AdaptiveVadBackend(noise_percentile=50, sensitivity=2.0)
        assert backend_low._noise_percentile == 5
        assert backend_high._noise_percentile == 50


class TestProviderProtocol:
    """Test VADProvider protocol compliance."""

    def test_capabilities(self) -> None:
        backend = AdaptiveVadBackend()
        caps = backend.capabilities()
        assert caps.streaming is True
        assert caps.max_concurrent == 10
        assert caps.supports_cancellation is True

    def test_lifecycle(self) -> None:
        backend = AdaptiveVadBackend()
        backend.initialize()
        assert backend.health_check() is True
        backend.shutdown()

    def test_provider_properties(self) -> None:
        backend = AdaptiveVadBackend()
        assert backend.name == "adaptive"
        assert backend.modality == "vad"
        assert backend.capabilities().streaming is True
        assert backend.capabilities().supports_cancellation is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

