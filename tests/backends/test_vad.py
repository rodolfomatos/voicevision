"""Tests for WebrtcVadBackend using mocks.

No webrtcvad binary needed — tests mock the import and vad.is_speech calls.
"""

from __future__ import annotations

import builtins
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import voicevision.backends.vad as vad_module
from voicevision.backends.vad import WebrtcVadBackend
from voicevision.errors import BackendExecutionError, BackendNotAvailableError


def make_pcm(frames: int, sample_rate: int = 16000, speech: bool = True) -> bytes:
    """Generate synthetic PCM16 frames.

    speech=True: alternating pattern that webrtcvad typically classifies as speech
    speech=False: silence (zeros)
    """
    frame_bytes = (16000 * 30 // 1000) * 2  # 960 bytes at 16kHz
    if speech:
        # Alternating pattern that triggers speech detection
        pattern = bytes([i % 256 for i in range(frame_bytes)])
    else:
        pattern = bytes(frame_bytes)
    return pattern * frames


def make_vad_mock() -> tuple[MagicMock, MagicMock]:
    """Create a mocked webrtcvad module and Vad instance."""
    vad_mock = MagicMock()
    vad_instance = MagicMock()
    vad_mock.Vad.return_value = vad_instance
    return vad_mock, vad_instance


@contextmanager
def patch_webrtcvad(vad_mock: MagicMock):
    """Context manager to patch the webrtcvad import in the vad module."""
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "webrtcvad":
            return vad_mock
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        yield


# -- construction ----------------------------------------------------------


class TestConstruction:
    def test_requires_valid_aggressiveness(self) -> None:
        with pytest.raises(ValueError, match="0-3"):
            WebrtcVadBackend(aggressiveness=4)
        with pytest.raises(ValueError, match="0-3"):
            WebrtcVadBackend(aggressiveness=-1)

    def test_requires_valid_sample_rate(self) -> None:
        with pytest.raises(ValueError, match="8000, 16000, 32000, or 48000"):
            WebrtcVadBackend(sample_rate=22050)

    def test_requires_positive_silence_ms(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            WebrtcVadBackend(silence_ms=0)

    def test_requires_positive_max_utterance_ms(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            WebrtcVadBackend(max_utterance_ms=0)

    def test_defaults(self) -> None:
        backend = WebrtcVadBackend()
        assert backend._aggressiveness == 2
        assert backend._sample_rate == 16000
        assert backend._silence_ms == 500
        assert backend._max_utterance_ms == 30000

    def test_available_is_false_without_webrtcvad(self) -> None:
        import sys
        # Temporarily remove webrtcvad from sys.modules to simulate it not being installed
        webrtcvad_mod = sys.modules.pop("webrtcvad", None)
        try:
            assert WebrtcVadBackend.available() is False
        finally:
            if webrtcvad_mod is not None:
                sys.modules["webrtcvad"] = webrtcvad_mod


# -- segmentation ----------------------------------------------------------


class TestSegmentation:
    """Tests using a mocked webrtcvad.Vad."""

    def test_silence_yields_nothing(self) -> None:
        """All-silence stream yields no utterances."""
        vad_mock, vad_instance = make_vad_mock()
        vad_instance.is_speech.return_value = False
        with patch_webrtcvad(vad_mock):
            backend = WebrtcVadBackend()
            pcm = make_pcm(100, speech=False)
            results = list(backend.segment(pcm))
            assert results == []

    def test_single_utterance(self) -> None:
        """Speech followed by silence yields one utterance."""
        vad_mock, vad_instance = make_vad_mock()
        # First 10 frames speech, then 20 silence
        vad_instance.is_speech.side_effect = [True] * 10 + [False] * 20
        with patch_webrtcvad(vad_mock):
            backend = WebrtcVadBackend(silence_ms=500)  # ~17 frames silence to close
            pcm = make_pcm(30)
            results = list(backend.segment(pcm))
            assert len(results) == 1
            start, end = results[0]
            assert start == 0
            assert end > 0

    def test_multiple_utterances(self) -> None:
        """Speech-silence-speech yields two utterances."""
        vad_mock, vad_instance = make_vad_mock()
        # 10 speech, 20 silence, 10 speech, 20 silence
        vad_instance.is_speech.side_effect = [True] * 10 + [False] * 20 + [True] * 10 + [False] * 20
        with patch_webrtcvad(vad_mock):
            backend = WebrtcVadBackend(silence_ms=500)
            pcm = make_pcm(60)
            results = list(backend.segment(pcm))
            assert len(results) == 2

    def test_silence_frames_config(self) -> None:
        """silence_ms controls how many silent frames close an utterance."""
        vad_mock, vad_instance = make_vad_mock()
        # 5 speech, 5 silence, 5 speech
        vad_instance.is_speech.side_effect = [True] * 5 + [False] * 5 + [True] * 5
        with patch_webrtcvad(vad_mock):
            # silence_ms=150 -> 5 frames (5*30=150)
            backend = WebrtcVadBackend(silence_ms=150)
            pcm = make_pcm(15)
            results = list(backend.segment(pcm))
            # Should split into two utterances (5 frames silence closes first)
            assert len(results) == 2

    def test_max_utterance_force_closes(self) -> None:
        """max_utterance_ms forces utterance closure (runaway protection)."""
        vad_mock, vad_instance = make_vad_mock()
        vad_instance.is_speech.return_value = True  # Continuous speech
        with patch_webrtcvad(vad_mock):
            # max_utterance_ms=600 -> 20 frames
            backend = WebrtcVadBackend(max_utterance_ms=600)
            pcm = make_pcm(50)  # 50 frames of speech
            results = list(backend.segment(pcm))
            # Should force-close at 20 frames, then start new
            assert len(results) >= 2
            # Each utterance <= max_frames * frame_bytes
            frame_bytes = 960
            max_bytes = 20 * frame_bytes
            for start, end in results:
                assert end - start <= max_bytes

    def test_empty_input(self) -> None:
        """Empty PCM yields no utterances."""
        vad_mock, _ = make_vad_mock()
        with patch_webrtcvad(vad_mock):
            backend = WebrtcVadBackend()
            results = list(backend.segment(b""))
            assert results == []

    def test_invalid_pcm_length_raises(self) -> None:
        """PCM not multiple of frame size raises ValueError."""
        backend = WebrtcVadBackend()
        bad_pcm = b"x" * 100  # Not multiple of 960
        with pytest.raises(ValueError, match="not a multiple of frame size"):
            list(backend.segment(bad_pcm))

    def test_stream_ends_in_utterance_emits_final(self) -> None:
        """Stream ending during speech emits the final utterance."""
        vad_mock, vad_instance = make_vad_mock()
        vad_instance.is_speech.return_value = True
        with patch_webrtcvad(vad_mock):
            backend = WebrtcVadBackend()
            pcm = make_pcm(10)  # 10 frames, then stream ends
            results = list(backend.segment(pcm))
            assert len(results) == 1
            start, end = results[0]
            assert start == 0
            assert end == len(pcm)

    def test_silence_does_not_emit_utterance(self) -> None:
        """Pure silence never emits an utterance."""
        vad_mock, vad_instance = make_vad_mock()
        vad_instance.is_speech.return_value = False
        with patch_webrtcvad(vad_mock):
            backend = WebrtcVadBackend()
            pcm = make_pcm(100, speech=False)
            results = list(backend.segment(pcm))
            assert results == []

    def test_aggressiveness_levels(self) -> None:
        """Different aggressiveness levels are passed to webrtcvad."""
        for agg in range(4):
            vad_mock, vad_instance = make_vad_mock()
            vad_instance.is_speech.return_value = False
            with patch_webrtcvad(vad_mock):
                backend = WebrtcVadBackend(aggressiveness=agg)
                list(backend.segment(make_pcm(1)))
                vad_mock.Vad.assert_called_with(agg)

    def test_sample_rate_validation(self) -> None:
        """Only 8000, 16000, 32000, 48000 are accepted."""
        for rate in (8000, 16000, 32000, 48000):
            backend = WebrtcVadBackend(sample_rate=rate)
            assert backend._sample_rate == rate

        with pytest.raises(ValueError):
            WebrtcVadBackend(sample_rate=22050)


# -- integration ----------------------------------------------------------


import os

@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("VOICEVISION_VAD_TEST"),
    reason="set VOICEVISION_VAD_TEST=1 to run with real webrtcvad",
)
def test_real_vad_segments() -> None:
    """Opt-in test with real webrtcvad."""
    import webrtcvad
    assert webrtcvad  # Just verify import works
    # Real test would go here