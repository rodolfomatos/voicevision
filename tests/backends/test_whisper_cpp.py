"""Tests for WhisperCppBackend and the audio format contract.

No whisper.cpp binary and no model file are needed: the fake child stands in for
the CLI, and the WAV fixtures are generated in-process.
"""

from __future__ import annotations

import dataclasses
import io
import wave

import pytest

from tests.support.fake_child import (
    WHISPER_BAD_MODEL,
    WHISPER_BLANK_AUDIO,
    WHISPER_ECHO_WAV,
    WHISPER_EMPTY,
    WHISPER_TIMESTAMPS,
    WHISPER_TO_FILE,
    WHISPER_TRANSCRIPT,
    build_argv,
)
from voicevision.audio import (
    AudioFormatError,
    WavInfo,
    pcm16_to_wav,
    read_wav_info,
    require_whisper_format,
)
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.errors import BackendExecutionError, BackendNotAvailableError

# -- fixtures --------------------------------------------------------------


def make_wav(
    *, seconds: float = 1.0, rate: int = 16_000, channels: int = 1, width: int = 2
) -> bytes:
    """A real WAV file of silence. Silence is fine — the fake child does not care."""
    frames = int(rate * seconds)
    payload = b"\x00\x00" * frames * channels
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(payload)
    return buffer.getvalue()


@pytest.fixture
def good_wav() -> bytes:
    return make_wav()


def fake_backend(behavior: str, **kwargs: object) -> WhisperCppBackend:
    """A WhisperCppBackend whose binary is the fake child."""
    backend = WhisperCppBackend(
        model=kwargs.pop("model", "/models/whisper-base.bin"),
        binary="whisper-cli",
        **kwargs,  # type: ignore[arg-type]
    )
    # Replace argv with the fake child, keeping whisper.cpp's own flags in front
    # so arg construction stays under test.
    backend._argv = [*build_argv(behavior), *backend._argv[1:]]
    return backend


# -- audio format contract -------------------------------------------------


class TestWavInfo:
    def test_reads_header(self, good_wav: bytes) -> None:
        info = read_wav_info(good_wav)
        assert info.channels == 1
        assert info.sample_rate == 16_000
        assert info.sample_width == 2
        assert info.frames == 16_000

    def test_duration(self, good_wav: bytes) -> None:
        assert read_wav_info(good_wav).duration_seconds == pytest.approx(1.0)

    def test_describe_is_human_readable(self, good_wav: bytes) -> None:
        assert "1ch" in read_wav_info(good_wav).describe()

    def test_not_a_wav_raises_audio_format_error(self) -> None:
        with pytest.raises(AudioFormatError, match="not a readable WAV"):
            read_wav_info(b"this is not audio at all")

    def test_empty_input_raises(self) -> None:
        with pytest.raises(AudioFormatError):
            read_wav_info(b"")

    def test_pcm16_to_wav_roundtrips(self) -> None:
        pcm = b"\x01\x02" * 100
        info = read_wav_info(pcm16_to_wav(pcm, sample_rate=16_000))
        assert info.sample_rate == 16_000
        assert info.frames == 100

    def test_wav_info_is_immutable(self) -> None:
        """A mutated WavInfo would silently describe the wrong audio."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            WavInfo(1, 2, 16_000, 1).channels = 2  # type: ignore[misc]


class TestFormatValidation:
    def test_accepts_correct_format(self, good_wav: bytes) -> None:
        assert require_whisper_format(good_wav).sample_rate == 16_000

    def test_wrong_sample_rate_names_the_actual_rate(self) -> None:
        """The whole point: name what was actually seen, do not resample."""
        wrong = make_wav(rate=44_100)
        with pytest.raises(AudioFormatError) as exc:
            require_whisper_format(wrong)
        message = str(exc.value)
        assert "44100Hz" in message
        assert "16000Hz" in message
        assert "capture layer" in message

    def test_stereo_is_rejected(self) -> None:
        with pytest.raises(AudioFormatError) as exc:
            require_whisper_format(make_wav(channels=2))
        assert "channels" in str(exc.value)

    def test_8bit_is_rejected(self) -> None:
        with pytest.raises(AudioFormatError) as exc:
            require_whisper_format(make_wav(width=1))
        assert "8-bit" in str(exc.value)

    def test_reports_every_problem_at_once(self) -> None:
        bad = make_wav(rate=8_000, channels=2)
        with pytest.raises(AudioFormatError) as exc:
            require_whisper_format(bad)
        message = str(exc.value)
        assert "8000Hz" in message
        assert "channels" in message


# -- construction ----------------------------------------------------------


class TestConstruction:
    def test_requires_a_model_path(self) -> None:
        with pytest.raises(ValueError, match="does not download"):
            WhisperCppBackend(model="")

    def test_name_is_stable(self) -> None:
        assert WhisperCppBackend(model="/m.bin", binary="whisper-cli").name == "whispercpp"

    def test_argv_contains_model_and_stdin_flag(self) -> None:
        backend = WhisperCppBackend(model="/models/base.bin", binary="whisper-cli")
        argv = backend.command_line
        assert "-m /models/base.bin" in argv
        assert "-f -" in argv
        assert "-otxt" in argv
        assert "-of -" in argv

    def test_language_is_passed_through(self) -> None:
        backend = WhisperCppBackend(model="/m.bin", language="pt", binary="whisper-cli")
        assert "-l pt" in backend.command_line

    def test_default_language_is_english(self) -> None:
        assert "-l en" in WhisperCppBackend(model="/m.bin", binary="whisper-cli").command_line

    def test_extra_args_are_appended(self) -> None:
        backend = WhisperCppBackend(
            model="/m.bin", binary="whisper-cli", extra_args=["--beam-size", "5"]
        )
        assert backend.command_line.rstrip().endswith("--beam-size 5")

    def test_timestamps_are_suppressed(self) -> None:
        """-nt keeps timestamps out of the transcript in the first place."""
        assert "-nt" in WhisperCppBackend(model="/m.bin", binary="whisper-cli").command_line

    def test_install_hint_names_the_build_step(self) -> None:
        assert "cmake" in WhisperCppBackend.install_hint

    def test_available_is_false_without_binary(self) -> None:
        assert WhisperCppBackend.available() is False

    def test_alternate_binary_is_probed(self, monkeypatch) -> None:
        """Older whisper.cpp builds ship `main`, not `whisper-cli`."""
        monkeypatch.setattr(
            "voicevision.backends.whisper_cpp.shutil.which",
            lambda cmd: "/usr/bin/main" if cmd == "main" else None,
        )
        assert WhisperCppBackend.available() is True


# -- transcription ---------------------------------------------------------


class TestTranscribe:
    def test_returns_stripped_text(self, good_wav: bytes) -> None:
        backend = fake_backend(WHISPER_TRANSCRIPT)
        assert backend.transcribe(good_wav) == "hello there general kenobi"

    def test_strips_timestamps_when_flag_ignored(self, good_wav: bytes) -> None:
        """Forks vary; output must not leak `[00:00:00.000 --> ...]` to callers."""
        backend = fake_backend(WHISPER_TIMESTAMPS)
        result = backend.transcribe(good_wav)
        assert "-->" not in result
        assert "[" not in result
        assert "Hello there." in result
        assert "General Kenobi." in result

    def test_empty_transcript_returns_empty_string(self, good_wav: bytes) -> None:
        """Silence is a result, not an error. The caller decides what to do."""
        backend = fake_backend(WHISPER_EMPTY)
        assert backend.transcribe(good_wav) == ""

    def test_blank_audio_markers_removed(self, good_wav: bytes) -> None:
        backend = fake_backend(WHISPER_BLANK_AUDIO)
        result = backend.transcribe(good_wav)
        assert "BLANK_AUDIO" not in result
        assert "shoe" in result

    def test_transcript_file_notice_discarded(self, good_wav: bytes) -> None:
        """A build that writes a file and says so must not yield the filename."""
        backend = fake_backend(WHISPER_TO_FILE)
        assert backend.transcribe(good_wav) == ""

    def test_wav_reaches_the_child_intact(self, good_wav: bytes) -> None:
        backend = fake_backend(WHISPER_ECHO_WAV)
        assert backend.transcribe(good_wav) == str(len(good_wav))

    def test_model_failure_raises_with_stderr(self, good_wav: bytes) -> None:
        backend = fake_backend(WHISPER_BAD_MODEL)
        with pytest.raises(BackendExecutionError) as exc:
            backend.transcribe(good_wav)
        assert "failed to open model file" in exc.value.stderr
        assert exc.value.returncode == 1

    def test_missing_binary_raises_not_available(self, good_wav: bytes) -> None:
        backend = WhisperCppBackend(model="/m.bin", binary="whisper-cli")
        backend._argv = ["whisper-cli-does-not-exist-xyz"]
        with pytest.raises(BackendNotAvailableError):
            backend.transcribe(good_wav)


# -- validation happens before spawning -------------------------------------


class TestValidationPrecedesExecution:
    def test_bad_format_never_reaches_whisper(self) -> None:
        """A format bug is the caller's; whisper.cpp must not be bothered."""
        backend = fake_backend(WHISPER_TRANSCRIPT)
        with pytest.raises(AudioFormatError):
            backend.transcribe(make_wav(rate=22_050))
        assert backend.last_pid is None

    def test_kwargs_do_not_silently_change_argv(self, good_wav: bytes) -> None:
        """Per-call overrides belong on the constructor so they land in argv."""
        backend = fake_backend(WHISPER_TRANSCRIPT)
        before = backend.command_line
        backend.transcribe(good_wav, language="fr", temperature=0.9)
        assert backend.command_line == before


# -- integration -----------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not __import__("os").environ.get("VOICEVISION_WHISPER_MODEL"),
    reason="set VOICEVISION_WHISPER_MODEL to run against a real whisper.cpp",
)
def test_real_whisper_transcribes() -> None:
    """Opt-in. Requires a built whisper.cpp and a downloaded model."""
    import os

    backend = WhisperCppBackend(model=os.environ["VOICEVISION_WHISPER_MODEL"])
    assert backend.available()
    result = backend.transcribe(make_wav(seconds=0.5))
    assert isinstance(result, str)
