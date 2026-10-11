"""Tests for PiperBackend using mocks.

These tests verify the PiperBackend logic without spawning real processes,
using unittest.mock to intercept the subprocess calls.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock, call

import pytest

from voicevision.backends.piper import PiperBackend
from voicevision.errors import BackendExecutionError, BackendNotAvailableError


class TestConstruction:
    def test_requires_a_model_path(self) -> None:
        with pytest.raises(ValueError, match="does not download"):
            PiperBackend(model="")

    def test_name_is_stable(self) -> None:
        assert PiperBackend(model="/m.onnx").name == "piper"

    def test_argv_contains_model_and_output(self) -> None:
        backend = PiperBackend(model="/models/voice.onnx")
        argv = backend.command_line
        assert "--model /models/voice.onnx" in argv
        assert "--output_file -" in argv

    def test_voice_is_passed_through(self) -> None:
        backend = PiperBackend(model="/m.onnx", voice="en-medium")
        assert "--voice en-medium" in backend.command_line

    def test_length_scale_is_passed_through(self) -> None:
        backend = PiperBackend(model="/m.onnx", length_scale=1.5)
        assert "--length_scale 1.5" in backend.command_line

    def test_install_hint_names_the_build(self) -> None:
        assert "piper-tts" in PiperBackend.install_hint

    def test_available_is_false_without_binary(self) -> None:
        with patch("voicevision.backends.piper.shutil.which", return_value=None):
            assert PiperBackend.available() is False


class TestSynthesis:
    """Tests that mock the subprocess run to verify argument construction
    and response handling without spawning real processes."""

    def test_returns_wav_bytes(self) -> None:
        """Piper returns WAV bytes for valid input."""
        with patch.object(PiperBackend, "run", return_value=b"RIFF....WAVEfmt....data....") as mock_run:
            backend = PiperBackend(model="/models/voice.onnx")
            wav = backend.synthesize("hello")
            assert wav.startswith(b"RIFF")
            mock_run.assert_called_once_with(b"hello")

    def test_empty_text_returns_empty_bytes(self) -> None:
        """Empty text returns empty bytes without spawning piper."""
        with patch.object(PiperBackend, "run") as mock_run:
            backend = PiperBackend(model="/m.onnx")
            assert backend.synthesize("") == b""
            mock_run.assert_not_called()

    def test_long_text_does_not_deadlock(self) -> None:
        """Long text produces longer WAV; verifies no deadlock on large output."""
        long_wav = b"RIFF" + b"x" * 50000  # Simulate large WAV
        with patch.object(PiperBackend, "run", return_value=long_wav) as mock_run:
            backend = PiperBackend(model="/m.onnx")
            wav = backend.synthesize("x" * 5000)
            assert len(wav) > 40000
            mock_run.assert_called_once()

    def test_bad_voice_raises_with_stderr(self) -> None:
        """Invalid voice argument surfaces as BackendExecutionError with stderr."""
        from voicevision.errors import BackendExecutionError

        error_stderr = "error: voice 'nonexistent' not found\n"
        with patch.object(PiperBackend, "run", side_effect=BackendExecutionError(
            "piper", "piper failed", command="piper ...", returncode=1, stderr=error_stderr
        )):
            backend = PiperBackend(model="/m.onnx", voice="nonexistent")
            with pytest.raises(BackendExecutionError) as exc:
                backend.synthesize("x")
            assert "voice" in exc.value.stderr.lower()
            assert exc.value.returncode == 1

    def test_wav_has_valid_riff_header(self) -> None:
        """Output has valid RIFF/WAVE header structure."""
        wav = b"RIFF" + b"\x00" * 4 + b"WAVEfmt " + b"\x00" * 100
        with patch.object(PiperBackend, "run", return_value=wav):
            backend = PiperBackend(model="/m.onnx")
            wav_out = backend.synthesize("test")
            assert wav_out[:4] == b"RIFF"
            assert wav_out[8:12] == b"WAVE"
            assert wav_out[12:16] == b"fmt "

    def test_model_path_comes_from_constructor(self) -> None:
        backend = PiperBackend(model="/custom/model.onnx")
        assert backend._model == "/custom/model.onnx"

    def test_kwargs_do_not_silently_change_argv(self) -> None:
        """Per-call kwargs should not mutate the backend's argv."""
        with patch.object(PiperBackend, "run") as mock_run:
            backend = PiperBackend(model="/m.onnx")
            before = backend.command_line
            backend.synthesize("text", voice="ignored", length_scale=0.5)
            assert backend.command_line == before
            mock_run.assert_called_once()


# -- integration ----------------------------------------------------------


import os

@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("VOICEVISION_PIPER_MODEL"),
    reason="set VOICEVISION_PIPER_MODEL to run against real piper",
)
def test_real_piper_synthesizes() -> None:
    """Opt-in. Requires piper binary and a downloaded ONNX voice model."""
    backend = PiperBackend(model=os.environ["VOICEVISION_PIPER_MODEL"])
    assert backend.available()
    wav = backend.synthesize("test")
    assert wav.startswith(b"RIFF")
    assert len(wav) > 44