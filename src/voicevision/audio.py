"""Audio helpers.

Minimal WAV handling shared by the STT backends and the capture layer. Built on
the stdlib `wave` module: no dependency for something this small.

The rule throughout this module is **never resample silently**. A wrong sample
rate is reported with the value that was actually seen, because a caller who
assumes their capture produced 16 kHz and is wrong will otherwise spend hours
debugging the model's output quality instead of their own capture code.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

#: whisper.cpp expects 16 kHz. Anything else must be rejected, not converted.
WHISPER_SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class WavInfo:
    """What a WAV header says about the audio it contains."""

    channels: int
    sample_width: int
    sample_rate: int
    frames: int

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate == 0:
            return 0.0
        return self.frames / float(self.sample_rate)

    def describe(self) -> str:
        return (
            f"{self.channels}ch {self.sample_width * 8}-bit "
            f"{self.sample_rate}Hz ({self.duration_seconds:.2f}s)"
        )


class AudioFormatError(ValueError):
    """Audio is not in the format the caller promised.

    Deliberately a `ValueError` subclass: it means the caller handed us
    something wrong, not that a backend or the system is broken.
    """


def read_wav_info(data: bytes) -> WavInfo:
    """Parse a WAV header.

    Raises:
        AudioFormatError: if the bytes are not a readable WAV file.
    """
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            return WavInfo(
                channels=wav.getnchannels(),
                sample_width=wav.getsampwidth(),
                sample_rate=wav.getframerate(),
                frames=wav.getnframes(),
            )
    except (wave.Error, EOFError) as exc:
        raise AudioFormatError(f"not a readable WAV file: {exc}") from exc


def require_whisper_format(data: bytes) -> WavInfo:
    """Validate that `data` is WAV that whisper.cpp can consume.

    whisper.cpp wants 16 kHz mono PCM16. Anything else is refused with the actual
    values, because resampling here would hide a bug in the capture layer and
    produce a transcript that is subtly wrong rather than obviously broken.

    Raises:
        AudioFormatError: naming what was actually seen.
    """
    info = read_wav_info(data)
    problems: list[str] = []

    if info.sample_rate != WHISPER_SAMPLE_RATE:
        problems.append(f"sample rate is {info.sample_rate}Hz, expected {WHISPER_SAMPLE_RATE}Hz")
    if info.channels != 1:
        problems.append(f"{info.channels} channels, expected mono")
    if info.sample_width != 2:
        problems.append(f"{info.sample_width * 8}-bit samples, expected 16-bit PCM")

    if problems:
        raise AudioFormatError(
            "audio is not in the format whisper.cpp expects: "
            + "; ".join(problems)
            + ". Resample at the capture layer, not here."
        )
    return info


def pcm16_to_wav(
    pcm: bytes,
    *,
    sample_rate: int = WHISPER_SAMPLE_RATE,
    channels: int = 1,
) -> bytes:
    """Wrap raw PCM16 in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
