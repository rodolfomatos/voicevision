"""Tests for voicevision.listen — microphone → VAD → STT → text on stdout.

No real microphone, no sounddevice, no webrtcvad, and no whisper.cpp binary
are needed: everything is mocked or replaced with the fake child.
"""

from __future__ import annotations

import os
import sys
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

from tests.support.fake_child import (
    WHISPER_EMPTY,
    WHISPER_TRANSCRIPT,
    build_argv,
)
from voicevision.audio import pcm16_to_wav
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.errors import BackendExecutionError, BackendNotAvailableError
from voicevision.listen import (
    FRAME_BYTES,
    ListenConfig,
    ListenError,
    PreRollBuffer,
    _capture_fixed_seconds,
    _capture_until_utterance,
    _env_float,
    _env_int,
    _normalize_text,
    _pre_roll_bytes,
    _strip_wake_word,
    _transcribe_pcm,
    _wake_word_detected,
    load_config,
    run,
)

# -- env var parsing ---------------------------------------------------------


class TestEnvParsing:
    def test_env_int_default(self, monkeypatch: Any) -> None:
        monkeypatch.delenv("VOICEVISION_VAD_AGGRESSIVENESS", raising=False)
        assert _env_int("VOICEVISION_VAD_AGGRESSIVENESS", 2) == 2

    def test_env_int_value(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("VOICEVISION_VAD_AGGRESSIVENESS", "3")
        assert _env_int("VOICEVISION_VAD_AGGRESSIVENESS", 2) == 3

    def test_env_int_invalid_falls_back(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("VOICEVISION_VAD_AGGRESSIVENESS", "not-an-int")
        assert _env_int("VOICEVISION_VAD_AGGRESSIVENESS", 2) == 2

    def test_env_float_default(self, monkeypatch: Any) -> None:
        monkeypatch.delenv("VOICEVISION_MAX_RECORD_SECONDS", raising=False)
        assert _env_float("VOICEVISION_MAX_RECORD_SECONDS", 60.0) == 60.0

    def test_env_float_value(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("VOICEVISION_MAX_RECORD_SECONDS", "10.5")
        assert _env_float("VOICEVISION_MAX_RECORD_SECONDS", 60.0) == 10.5


# -- config loading ----------------------------------------------------------


class TestLoadConfig:
    def test_defaults(self, clean_env: Any) -> None:
        cfg = load_config()
        assert cfg.stt_model == ""
        assert cfg.stt_language == "en"
        assert cfg.vad_aggressiveness == 2
        assert cfg.vad_silence_ms == 500
        assert cfg.vad_max_utterance_ms == 30_000
        assert cfg.max_record_seconds == 60.0
        assert cfg.fixed_seconds == 0.0
        assert cfg.wake_word == ""
        assert cfg.pre_roll_seconds == 0.0

    def test_from_env(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("VOICEVISION_STT_MODEL", "/models/whisper-base.bin")
        monkeypatch.setenv("VOICEVISION_STT_LANGUAGE", "pt")
        monkeypatch.setenv("VOICEVISION_VAD_AGGRESSIVENESS", "1")
        monkeypatch.setenv("VOICEVISION_VAD_SILENCE_MS", "300")
        monkeypatch.setenv("VOICEVISION_MAX_RECORD_SECONDS", "30")
        monkeypatch.setenv("VOICEVISION_WAKE_WORD", "olá ambrósio")
        monkeypatch.setenv("VOICEVISION_PRE_ROLL_SECONDS", "5")
        cfg = load_config()
        assert cfg.stt_model == "/models/whisper-base.bin"
        assert cfg.stt_language == "pt"
        assert cfg.vad_aggressiveness == 1
        assert cfg.vad_silence_ms == 300
        assert cfg.max_record_seconds == 30.0
        assert cfg.wake_word == "olá ambrósio"
        assert cfg.pre_roll_seconds == 5.0


# -- sounddevice fake --------------------------------------------------------


def _install_fake_sounddevice(monkeypatch: Any, frames: list[bytes]) -> None:
    """Inject a fake sounddevice module so `import sounddevice` inside
    `_capture_until_utterance` gets the fake instead of the real library."""

    class FakeInputStream:
        """Context-manager stand-in for sounddevice.InputStream.

        Yields one PCM frame per read(), then silence.
        """

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._frames = frames
            self._index = 0

        def __enter__(self) -> FakeInputStream:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self, blocksize: int) -> tuple[bytes, bool]:
            if self._index < len(self._frames):
                frame = self._frames[self._index]
                self._index += 1
                return (frame, False)
            return (b"", False)

    fake = ModuleType("sounddevice")
    fake.InputStream = FakeInputStream  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake)


class FakeVadBackend:
    """Fake VAD backend for testing. Returns configured utterances in order.
    Each element of the utterance_list is itself a list of (start, end) tuples,
    or [] to indicate no utterance detected.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.utterance_list = list(kwargs.get("utterances", [[(0, FRAME_BYTES)]]))
        self.call_count = 0

    def segment(self, pcm: bytes) -> list[tuple[int, int]]:
        self.call_count += 1
        if self.utterance_list:
            return self.utterance_list.pop(0)
        return []


# -- capture -----------------------------------------------------------------


class TestCapture:
    def test_returns_utterance_when_vad_detects(
        self,
        monkeypatch: Any,
    ) -> None:
        """One frame of audio, VAD reports an utterance covering it all."""
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES])
        fake_vad = FakeVadBackend(utterances=[[(0, FRAME_BYTES)]])
        with patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad):
            pcm = _capture_until_utterance(
                ListenConfig(max_record_seconds=60.0),
            )
        assert pcm == b"\x00" * FRAME_BYTES

    def test_returns_empty_on_timeout(
        self,
        monkeypatch: Any,
    ) -> None:
        """VAD never detects speech; capture returns empty before the deadline."""
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES])
        fake_vad = FakeVadBackend(utterances=[])
        with patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad):
            pcm = _capture_until_utterance(
                ListenConfig(max_record_seconds=0.0),
            )
        assert pcm == b""

    def test_raises_listen_error_when_sounddevice_missing(
        self,
        monkeypatch: Any,
    ) -> None:
        """ImportError from sounddevice becomes a ListenError with a hint."""
        monkeypatch.setitem(sys.modules, "sounddevice", None)
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=FakeVadBackend()),
            pytest.raises(ListenError, match="sounddevice"),
        ):
            _capture_until_utterance(ListenConfig(max_record_seconds=60.0))

    def test_capture_fixed_seconds_returns_all_frames(
        self,
        monkeypatch: Any,
    ) -> None:
        """Fixed-duration capture returns the full number of frames."""
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES, b"\x01" * FRAME_BYTES])
        pcm = _capture_fixed_seconds(
            ListenConfig(fixed_seconds=0.12),  # 2 frames at 16 kHz 30 ms
        )
        assert pcm == b"\x00" * FRAME_BYTES + b"\x01" * FRAME_BYTES

    def test_capture_fixed_seconds_raises_when_sounddevice_missing(
        self,
        monkeypatch: Any,
    ) -> None:
        monkeypatch.setitem(sys.modules, "sounddevice", None)
        with pytest.raises(ListenError, match="sounddevice"):
            _capture_fixed_seconds(ListenConfig(fixed_seconds=5.0))


# -- transcription -----------------------------------------------------------


def _fake_stt(behavior: str) -> WhisperCppBackend:
    backend = WhisperCppBackend(
        model="/models/whisper-base.bin",
        binary="whisper-cli",
    )
    backend._argv = [*build_argv(behavior), *backend._argv[1:]]  # type: ignore[attr-defined]
    return backend


class TestTranscribe:
    def test_returns_stripped_text(self) -> None:
        wav = pcm16_to_wav(b"\x00" * FRAME_BYTES, sample_rate=16_000)
        with patch(
            "voicevision.listen.WhisperCppBackend",
            return_value=_fake_stt(WHISPER_TRANSCRIPT),
        ):
            text = _transcribe_pcm(wav, ListenConfig(stt_language="en"))
        assert text == "hello there general kenobi"

    def test_empty_transcript_returns_empty_string(self) -> None:
        wav = pcm16_to_wav(b"\x00" * FRAME_BYTES, sample_rate=16_000)
        with patch(
            "voicevision.listen.WhisperCppBackend",
            return_value=_fake_stt(WHISPER_EMPTY),
        ):
            text = _transcribe_pcm(wav, ListenConfig())
        assert text == ""

    def test_missing_whisper_raises_not_available(self) -> None:
        wav = pcm16_to_wav(b"\x00" * FRAME_BYTES, sample_rate=16_000)
        with (
            patch(
                "voicevision.listen.WhisperCppBackend",
                side_effect=BackendNotAvailableError(
                    "whispercpp",
                    "build whisper.cpp",
                ),
            ),
            pytest.raises(BackendNotAvailableError),
        ):
            _transcribe_pcm(wav, ListenConfig())


# -- run (orchestration) -----------------------------------------------------


class TestRun:
    def test_prints_transcript_and_returns_zero(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        with (
            patch(
                "voicevision.listen._capture_until_utterance",
                return_value=b"\x00" * FRAME_BYTES,
            ),
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="ola mundo",
            ),
        ):
            code = run(ListenConfig(stt_model="/models/whisper-base.bin"))
        assert code == 0
        out = capsys.readouterr().out.strip()
        assert out == "ola mundo"

    def test_no_speech_prints_stderr_and_returns_zero(
        self,
        capsys: Any,
    ) -> None:
        with patch(
            "voicevision.listen._capture_until_utterance",
            return_value=b"",
        ):
            code = run(ListenConfig(stt_model="/models/whisper-base.bin"))
        assert code == 0
        err = capsys.readouterr().err.strip()
        assert "no speech detected" in err

    def test_missing_stt_model_returns_two(
        self,
        capsys: Any,
    ) -> None:
        code = run(ListenConfig())
        assert code == 2
        err = capsys.readouterr().err.strip()
        assert "VOICEVISION_STT_MODEL" in err

    def test_transcribe_failure_returns_two(
        self,
        capsys: Any,
    ) -> None:
        with (
            patch(
                "voicevision.listen._capture_until_utterance",
                return_value=b"\x00" * FRAME_BYTES,
            ),
            patch(
                "voicevision.listen._transcribe_pcm",
                side_effect=BackendExecutionError(
                    "whispercpp",
                    "process exited non-zero",
                ),
            ),
        ):
            code = run(ListenConfig(stt_model="/models/whisper-base.bin"))
        assert code == 2
        err = capsys.readouterr().err.strip()
        assert "transcription failed" in err

    def test_fixed_seconds_uses_fixed_capture(
        self,
        capsys: Any,
    ) -> None:
        """When fixed_seconds > 0, _capture_fixed_seconds is used instead of VAD."""
        with (
            patch(
                "voicevision.listen._capture_fixed_seconds",
                return_value=b"\x00" * FRAME_BYTES,
            ) as mock_fixed,
            patch(
                "voicevision.listen._capture_until_utterance",
            ) as mock_vad,
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="ola mundo",
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    fixed_seconds=5.0,
                )
            )
        assert code == 0
        mock_fixed.assert_called_once()
        mock_vad.assert_not_called()
        out = capsys.readouterr().out.strip()
        assert out == "ola mundo"


# -- wake word ---------------------------------------------------------------


class TestNormalizeText:
    def test_lowercase(self) -> None:
        assert _normalize_text("OLÁ AMBRÓSIO") == "ola ambrosio"

    def test_strips_accents(self) -> None:
        assert _normalize_text("áéíóú") == "aeiou"

    def test_collapses_whitespace(self) -> None:
        assert _normalize_text("  olá   ambrósio  ") == "ola ambrosio"

    def test_removes_punctuation(self) -> None:
        assert _normalize_text("olá, ambrósio!") == "ola ambrosio"

    def test_keeps_digits(self) -> None:
        assert _normalize_text("ambrosio 2") == "ambrosio 2"

    def test_empty(self) -> None:
        assert _normalize_text("") == ""


class TestWakeWordDetection:
    def test_match_exact(self) -> None:
        assert _wake_word_detected("olá ambrósio", "olá ambrósio") is True

    def test_match_case_insensitive(self) -> None:
        assert _wake_word_detected("OLÁ AMBRÓSIO", "olá ambrósio") is True

    def test_match_with_accents(self) -> None:
        assert _wake_word_detected("ola ambrosio", "olá ambrósio") is True

    def test_match_substring(self) -> None:
        assert _wake_word_detected("olá ambrósio, como vais?", "olá ambrósio") is True

    def test_no_match(self) -> None:
        assert _wake_word_detected("ola mundo", "olá ambrósio") is False

    def test_empty_wake_word(self) -> None:
        assert _wake_word_detected("qualquer coisa", "") is False


class TestStripWakeWord:
    def test_strips_wake_word(self) -> None:
        result = _strip_wake_word("olá ambrósio como vais", "olá ambrósio")
        assert result == "como vais"

    def test_no_wake_word_returns_original(self) -> None:
        result = _strip_wake_word("ola mundo", "olá ambrósio")
        assert result == "ola mundo"


class TestPreRollBuffer:
    def test_push_and_get(self) -> None:
        buf = PreRollBuffer(100)
        buf.push(b"\x00" * 40)
        buf.push(b"\x01" * 40)
        assert buf.get() == b"\x00" * 40 + b"\x01" * 40
        assert buf.size() == 80

    def test_wraparound(self) -> None:
        buf = PreRollBuffer(100)
        buf.push(b"\x00" * 60)
        buf.push(b"\x01" * 60)  # overwrites first 20 bytes of the 60
        data = buf.get()
        assert len(data) == 100
        assert data[:40] == b"\x00" * 40  # tail of first push
        assert data[40:] == b"\x01" * 60  # all of second push

    def test_clear(self) -> None:
        buf = PreRollBuffer(100)
        buf.push(b"\x00" * 40)
        assert buf.size() == 40
        buf.clear()
        assert buf.size() == 0
        assert buf.get() == b""

    def test_max_bytes_zero(self) -> None:
        """max_bytes=0 means unlimited buffer."""
        buf = PreRollBuffer(0)
        buf.push(b"\x00" * 40)
        assert buf.size() == 40
        assert buf.get() == b"\x00" * 40

    def test_larger_than_buffer(self) -> None:
        buf = PreRollBuffer(40)
        buf.push(b"\x00" * 100)  # larger than buffer
        assert buf.size() == 40
        assert buf.get() == b"\x00" * 40  # only the tail


class TestPreRollBytes:
    def test_calculation(self) -> None:
        # 1 second at 16 kHz mono PCM16 = 32000 bytes
        assert _pre_roll_bytes(1.0) == 32000
        assert _pre_roll_bytes(2.0) == 64000
        assert _pre_roll_bytes(0.0) == 0


class TestWakeWordMode:
    def test_wake_word_detected_prints_remainder(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES])
        fake_vad = FakeVadBackend(utterances=[[(0, FRAME_BYTES)]])
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad),
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="olá ambrósio ligue as luzes",
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    max_record_seconds=5.0,
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip()
        assert out == "ligue as luzes"

    def test_wake_word_not_detected_prints_nothing(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES])
        fake_vad = FakeVadBackend(utterances=[[(0, FRAME_BYTES)]])
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad),
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="ola mundo",
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    max_record_seconds=0.0,
                )
            )
        assert code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == ""
        assert "wake word not detected" in captured.err.strip()

    def test_no_wake_word_config_runs_normally(
        self,
        capsys: Any,
    ) -> None:
        with (
            patch(
                "voicevision.listen._capture_until_utterance",
                return_value=b"\x00" * FRAME_BYTES,
            ),
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="ola mundo",
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="",
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip()
        assert out == "ola mundo"


class TestPreRollWakeWordMode:
    def test_pre_roll_prepended_to_utterance(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        """Pre-roll audio is included in the transcription when wake word is detected."""
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES, b"\x01" * FRAME_BYTES])
        fake_vad = FakeVadBackend(utterances=[[], [(0, FRAME_BYTES)]])
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad),
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="olá ambrósio ligue as luzes",
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    pre_roll_seconds=2.0,
                    max_record_seconds=5.0,
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip()
        assert out == "ligue as luzes"
        assert fake_vad.call_count == 2

    def test_pre_roll_zero_disabled(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        """pre_roll_seconds=0 means no pre-roll audio is included."""
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES])
        fake_vad = FakeVadBackend(utterances=[[(0, FRAME_BYTES)]])
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad),
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="olá ambrósio",
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    pre_roll_seconds=0.0,
                    max_record_seconds=5.0,
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip()
        assert out == "wake word detected"


# -- integration -------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("VOICEVISION_LISTEN_TEST"),
    reason="set VOICEVISION_LISTEN_TEST=1 to run with a real microphone and whisper.cpp",
)
def test_real_listen_transcribes() -> None:
    """Opt-in. Requires a microphone, sounddevice, webrtcvad, whisper-cli and a model."""
    code = run(
        ListenConfig(
            stt_model=os.environ["VOICEVISION_STT_MODEL"],
            max_record_seconds=10.0,
        )
    )
    assert code == 0
