"""Tests for voicevision.listen — microphone → VAD → STT → text on stdout.

No real microphone, no sounddevice, no webrtcvad, and no whisper.cpp binary
are needed: everything is mocked or replaced with the fake child.
"""

from __future__ import annotations

import json
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
from voicevision.history import HistoryStore
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
    main,
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
        assert cfg.quiet is False
        assert cfg.history_enabled is True
        assert cfg.history_file == ""
        assert cfg.continuous is False

    def test_from_env(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("VOICEVISION_STT_MODEL", "/models/whisper-base.bin")
        monkeypatch.setenv("VOICEVISION_STT_LANGUAGE", "pt")
        monkeypatch.setenv("VOICEVISION_VAD_AGGRESSIVENESS", "1")
        monkeypatch.setenv("VOICEVISION_VAD_SILENCE_MS", "300")
        monkeypatch.setenv("VOICEVISION_MAX_RECORD_SECONDS", "30")
        monkeypatch.setenv("VOICEVISION_WAKE_WORD", "olá ambrósio")
        monkeypatch.setenv("VOICEVISION_PRE_ROLL_SECONDS", "5")
        monkeypatch.setenv("VOICEVISION_QUIET", "1")
        monkeypatch.setenv("VOICEVISION_HISTORY_ENABLED", "0")
        monkeypatch.setenv("VOICEVISION_HISTORY_FILE", "/tmp/history.jsonl")
        monkeypatch.setenv("VOICEVISION_CONTINUOUS", "1")
        cfg = load_config()
        assert cfg.stt_model == "/models/whisper-base.bin"
        assert cfg.stt_language == "pt"
        assert cfg.vad_aggressiveness == 1
        assert cfg.vad_silence_ms == 300
        assert cfg.max_record_seconds == 30.0
        assert cfg.wake_word == "olá ambrósio"
        assert cfg.pre_roll_seconds == 5.0
        assert cfg.quiet is True
        assert cfg.history_enabled is False
        assert cfg.history_file == "/tmp/history.jsonl"
        assert cfg.continuous is True


# -- sounddevice fake --------------------------------------------------------


def _install_fake_sounddevice(
    monkeypatch: Any,
    frames: list[bytes],
    *,
    stop_after: bool = False,
) -> None:
    """Inject a fake sounddevice module so `import sounddevice` inside
    `_capture_until_utterance` gets the fake instead of the real library.

    When *stop_after* is true, the stream raises ``KeyboardInterrupt`` once the
    frames are exhausted — used to terminate the continuous listen loop.
    """

    class FakeInputStream:
        """Context-manager stand-in for sounddevice.InputStream.

        Yields one PCM frame per read(), then silence (or KeyboardInterrupt).
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
            if stop_after:
                raise KeyboardInterrupt
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


class TestListenModeJson:
    def test_json_output_prints_json(self, monkeypatch: Any, capsys: Any) -> None:
        """--json flag prints JSON with transcript, timestamp, language."""
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
                    json_output=True,
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["transcript"] == "ola mundo"
        assert "timestamp" in data
        assert data["language"] == "en"
        assert "audio_duration_seconds" in data
        assert "transcription_ms" in data

    def test_json_output_includes_pcm_duration(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        """--json includes audio_duration_seconds when --seconds is used."""
        with (
            patch(
                "voicevision.listen._capture_fixed_seconds",
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
                    fixed_seconds=2.0,
                    json_output=True,
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["transcript"] == "ola mundo"
        # 960 bytes at 16kHz mono PCM16 = 960 / (16000 * 2) = 0.03 seconds
        assert data["audio_duration_seconds"] == 960 / (16000 * 2)

    def test_json_output_includes_wake_word_detected(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        """--json with --wake-word includes wake_word_detected and wake_word."""
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES])
        fake_vad = FakeVadBackend(utterances=[[(0, FRAME_BYTES)]])
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad),
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="olá ambrósio, como está você?",
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    max_record_seconds=5.0,
                    json_output=True,
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip()
        data = json.loads(out)
        assert data["transcript"] == "como esta voce"  # wake word stripped (normalized)
        assert data["wake_word_detected"] is True
        assert data["wake_word"] == "olá ambrósio"

    def test_plain_text_when_no_json_flag(self, capsys: Any) -> None:
        """Without --json flag, plain text is printed."""
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
        # Should not be valid JSON
        import json

        try:
            json.loads(out)
            raise AssertionError("Should not be valid JSON")
        except json.JSONDecodeError:
            pass


# -- quiet mode --------------------------------------------------------------


class TestQuietMode:
    """T026: --quiet suppresses progress and outcome messages on stderr."""

    def test_default_is_not_quiet(self, clean_env: Any) -> None:
        assert load_config().quiet is False

    def test_reads_env_var(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("VOICEVISION_QUIET", "1")
        assert load_config().quiet is True

    def test_env_var_zero_is_not_quiet(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("VOICEVISION_QUIET", "0")
        assert load_config().quiet is False

    def test_cli_flag_sets_quiet(
        self,
        monkeypatch: Any,
    ) -> None:
        """--quiet on the command line overrides the config default."""
        captured: list[ListenConfig] = []

        def fake_run(config: ListenConfig) -> int:
            captured.append(config)
            return 0

        monkeypatch.setattr("voicevision.listen.run", fake_run)
        monkeypatch.setattr(
            sys,
            "argv",
            ["voicevision-listen", "--model", "/models/whisper-base.bin", "--quiet"],
        )
        with pytest.raises(SystemExit):
            main()
        assert captured
        assert captured[0].quiet is True

    def test_suppresses_progress_on_stderr(self, capsys: Any) -> None:
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
                ListenConfig(stt_model="/models/whisper-base.bin", quiet=True)
            )
        captured = capsys.readouterr()
        assert code == 0
        assert captured.out.strip() == "ola mundo"
        assert captured.err == ""

    def test_suppresses_no_speech_message(self, capsys: Any) -> None:
        with patch(
            "voicevision.listen._capture_until_utterance",
            return_value=b"",
        ):
            code = run(
                ListenConfig(stt_model="/models/whisper-base.bin", quiet=True)
            )
        captured = capsys.readouterr()
        assert code == 0
        assert captured.out == ""
        assert captured.err == ""

    def test_suppresses_wake_word_progress(self, monkeypatch: Any, capsys: Any) -> None:
        _install_fake_sounddevice(monkeypatch, [b"\x00" * FRAME_BYTES])
        fake_vad = FakeVadBackend(utterances=[])
        with patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    max_record_seconds=0.0,
                    quiet=True,
                )
            )
        captured = capsys.readouterr()
        assert code == 0
        assert captured.out == ""
        assert captured.err == ""

    def test_quiet_with_json_prints_only_json(self, capsys: Any) -> None:
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
                    json_output=True,
                    quiet=True,
                )
            )
        captured = capsys.readouterr()
        assert code == 0
        assert captured.err == ""
        data = json.loads(captured.out)
        assert data["transcript"] == "ola mundo"

    def test_capture_errors_still_reported(self, capsys: Any) -> None:
        """Fatal errors must not be silenced: exit code alone is ambiguous."""
        with patch(
            "voicevision.listen._capture_until_utterance",
            side_effect=ListenError("microphone unavailable"),
        ):
            code = run(
                ListenConfig(stt_model="/models/whisper-base.bin", quiet=True)
            )
        assert code == 2
        assert "microphone unavailable" in capsys.readouterr().err

    def test_transcription_errors_still_reported(self, capsys: Any) -> None:
        with (
            patch(
                "voicevision.listen._capture_until_utterance",
                return_value=b"\x00" * FRAME_BYTES,
            ),
            patch(
                "voicevision.listen._transcribe_pcm",
                side_effect=BackendExecutionError("whispercpp", "process failed"),
            ),
        ):
            code = run(
                ListenConfig(stt_model="/models/whisper-base.bin", quiet=True)
            )
        assert code == 2
        assert "transcription failed" in capsys.readouterr().err


# -- history integration -----------------------------------------------------


class TestHistoryIntegration:
    """T027: transcripts are persisted to a JSON Lines file."""

    def test_successful_transcription_appends_history(self, tmp_path: Any) -> None:
        history_file = tmp_path / "history.jsonl"
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
                    history_enabled=True,
                    history_file=str(history_file),
                )
            )
        assert code == 0
        entries = HistoryStore(history_file).read()
        assert len(entries) == 1
        assert entries[0].transcript == "ola mundo"
        assert entries[0].language == "en"

    def test_disabled_history_writes_nothing(self, tmp_path: Any) -> None:
        history_file = tmp_path / "history.jsonl"
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
                    history_enabled=False,
                    history_file=str(history_file),
                )
            )
        assert code == 0
        assert not history_file.exists()

    def test_history_write_failure_does_not_break(self, tmp_path: Any, capsys: Any) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
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
                    history_enabled=True,
                    history_file=str(blocker / "history.jsonl"),
                )
            )
        captured = capsys.readouterr()
        assert code == 0
        assert captured.out.strip() == "ola mundo"
        assert "could not write history" in captured.err

    def test_wake_word_records_the_wake_word(
        self,
        monkeypatch: Any,
        tmp_path: Any,
    ) -> None:
        history_file = tmp_path / "history.jsonl"
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
                    history_enabled=True,
                    history_file=str(history_file),
                )
            )
        assert code == 0
        entries = HistoryStore(history_file).read()
        assert len(entries) == 1
        assert entries[0].transcript == "ligue as luzes"
        assert entries[0].wake_word == "olá ambrósio"


# -- continuous wake word mode -----------------------------------------------


class TestContinuousMode:
    """T030: keep listening and print every wake word utterance."""

    def test_prints_each_detection(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        _install_fake_sounddevice(
            monkeypatch,
            [b"\x00" * FRAME_BYTES, b"\x00" * FRAME_BYTES],
            stop_after=True,
        )
        fake_vad = FakeVadBackend(
            utterances=[[(0, FRAME_BYTES)], [(0, FRAME_BYTES)]]
        )
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad),
            patch(
                "voicevision.listen._transcribe_pcm",
                side_effect=[
                    "olá ambrósio primeiro",
                    "olá ambrósio segundo",
                ],
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    continuous=True,
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip().splitlines()
        assert out == ["primeiro", "segundo"]

    def test_ignores_non_wake_word_utterances(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        _install_fake_sounddevice(
            monkeypatch,
            [b"\x00" * FRAME_BYTES, b"\x00" * FRAME_BYTES],
            stop_after=True,
        )
        fake_vad = FakeVadBackend(
            utterances=[[(0, FRAME_BYTES)], [(0, FRAME_BYTES)]]
        )
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad),
            patch(
                "voicevision.listen._transcribe_pcm",
                side_effect=["bom dia", "olá ambrósio abre a janela"],
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    continuous=True,
                )
            )
        assert code == 0
        out = capsys.readouterr().out.strip()
        assert out == "abre a janela"

    def test_duplicate_vad_ranges_are_transcribed_once(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        """A VAD that reports the same range twice must not duplicate output."""
        _install_fake_sounddevice(
            monkeypatch,
            [b"\x00" * FRAME_BYTES],
            stop_after=True,
        )
        fake_vad = FakeVadBackend(
            utterances=[[(0, FRAME_BYTES), (0, FRAME_BYTES)]]
        )
        with (
            patch("voicevision.listen.WebrtcVadBackend", return_value=fake_vad),
            patch(
                "voicevision.listen._transcribe_pcm",
                return_value="olá ambrósio uma vez",
            ) as transcribe,
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    continuous=True,
                )
            )
        assert code == 0
        assert transcribe.call_count == 1
        assert capsys.readouterr().out.strip() == "uma vez"

    def test_ctrl_c_returns_zero(self, monkeypatch: Any) -> None:
        _install_fake_sounddevice(monkeypatch, [], stop_after=True)
        with patch(
            "voicevision.listen.WebrtcVadBackend", return_value=FakeVadBackend()
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    continuous=True,
                )
            )
        assert code == 0

    def test_requires_wake_word(self, capsys: Any) -> None:
        code = run(
            ListenConfig(
                stt_model="/models/whisper-base.bin",
                continuous=True,
            )
        )
        assert code == 2
        assert "requires a wake word" in capsys.readouterr().err

    def test_quiet_suppresses_progress(self, monkeypatch: Any, capsys: Any) -> None:
        _install_fake_sounddevice(monkeypatch, [], stop_after=True)
        with patch(
            "voicevision.listen.WebrtcVadBackend", return_value=FakeVadBackend()
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/whisper-base.bin",
                    wake_word="olá ambrósio",
                    continuous=True,
                    quiet=True,
                )
            )
        assert code == 0
        assert capsys.readouterr().err == ""

    def test_records_history(
        self,
        monkeypatch: Any,
        tmp_path: Any,
    ) -> None:
        history_file = tmp_path / "history.jsonl"
        _install_fake_sounddevice(
            monkeypatch,
            [b"\x00" * FRAME_BYTES],
            stop_after=True,
        )
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
                    continuous=True,
                    history_enabled=True,
                    history_file=str(history_file),
                )
            )
        assert code == 0
        entries = HistoryStore(history_file).read()
        assert len(entries) == 1
        assert entries[0].transcript == "ligue as luzes"
        assert entries[0].wake_word == "olá ambrósio"


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


class TestSttModelSelection:
    def test_config_defaults_to_empty_model(self, clean_env: Any) -> None:
        cfg = load_config()
        assert cfg.stt_model == ""

    def test_config_reads_stt_model_from_env(
        self,
        monkeypatch: Any,
    ) -> None:
        monkeypatch.setenv("VOICEVISION_STT_MODEL", "/models/ggml-small.bin")
        cfg = load_config()
        assert cfg.stt_model == "/models/ggml-small.bin"

    def test_cli_model_flag_overrides_env(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        monkeypatch.setenv("VOICEVISION_STT_MODEL", "/models/ggml-base.bin")
        captured_models = []

        def capture_transcribe(pcm: bytes, config: ListenConfig) -> str:
            captured_models.append(config.stt_model)
            return "ola mundo"

        with (
            patch(
                "voicevision.listen._capture_fixed_seconds",
                return_value=b"\x00" * FRAME_BYTES,
            ),
            patch(
                "voicevision.listen._transcribe_pcm",
                side_effect=capture_transcribe,
            ),
        ):
            code = run(
                ListenConfig(
                    stt_model="/models/ggml-small.bin",
                    fixed_seconds=0.12,
                )
            )
        assert code == 0
        assert captured_models == ["/models/ggml-small.bin"]

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

    def test_non_matching_utterance_does_not_crash(
        self,
        monkeypatch: Any,
        capsys: Any,
    ) -> None:
        """Regression: hearing speech without the wake word used to raise AssertionError."""
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
                    max_record_seconds=0.1,
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
