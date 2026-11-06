"""Listen mode: microphone → VAD → STT → text on stdout.

A minimal, listen-only entry point for voicevision. Captures audio from the
microphone, segments it with WebRTC VAD, transcribes each utterance via
whisper.cpp, and prints the transcript to stdout. No LLM, no TTS — just
speech in, text out.

Designed to be invoked by an editor keybind (e.g. OpenCode) so the user can
speak instead of typing. Audio never leaves the local machine — no HTTP or
WebSocket surface, per the CLAUDE.md non-goal on network serving.

All heavy dependencies (sounddevice, webrtcvad, whisper.cpp) are probed
lazily so `import voicevision.listen` stays cheap and fails with a clear
install hint only when capture is actually attempted.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, replace
from typing import Final

from voicevision.audio import pcm16_to_wav
from voicevision.backends.vad import WebrtcVadBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.errors import BackendExecutionError, BackendNotAvailableError

#: whisper.cpp requires 16 kHz mono PCM16; VAD operates at the same rate.
DEFAULT_SAMPLE_RATE: Final = 16_000
#: VAD frame size: 30 ms at 16 kHz mono PCM16 = 960 bytes.
FRAME_BYTES: Final = (DEFAULT_SAMPLE_RATE * 30 // 1000) * 2


@dataclass
class ListenConfig:
    """Configuration for listen mode, read from the environment.

    All fields optional with sensible defaults. Environment variables use the
    ``VOICEVISION_`` prefix, consistent with the rest of voicevision.
    """

    stt_model: str = ""
    stt_language: str = "en"
    vad_aggressiveness: int = 2
    vad_silence_ms: int = 500
    vad_max_utterance_ms: int = 30_000
    max_record_seconds: float = 60.0
    fixed_seconds: float = 0.0


def _env_int(name: str, default: int) -> int:
    """Parse an integer env var, falling back to *default* on anything invalid."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Parse a float env var, falling back to *default* on anything invalid."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_config() -> ListenConfig:
    """Build a :class:`ListenConfig` from environment variables.

    Reads ``VOICEVISION_STT_MODEL``, ``VOICEVISION_STT_LANGUAGE``,
    ``VOICEVISION_VAD_AGGRESSIVENESS``, ``VOICEVISION_VAD_SILENCE_MS``,
    ``VOICEVISION_VAD_MAX_UTTERANCE_MS`` and
    ``VOICEVISION_MAX_RECORD_SECONDS``.
    """
    return ListenConfig(
        stt_model=os.environ.get("VOICEVISION_STT_MODEL", ""),
        stt_language=os.environ.get("VOICEVISION_STT_LANGUAGE", "en"),
        vad_aggressiveness=_env_int("VOICEVISION_VAD_AGGRESSIVENESS", 2),
        vad_silence_ms=_env_int("VOICEVISION_VAD_SILENCE_MS", 500),
        vad_max_utterance_ms=_env_int("VOICEVISION_VAD_MAX_UTTERANCE_MS", 30_000),
        max_record_seconds=_env_float("VOICEVISION_MAX_RECORD_SECONDS", 60.0),
        fixed_seconds=_env_float("VOICEVISION_FIXED_SECONDS", 0.0),
    )


class ListenError(RuntimeError):
    """Fatal listen-mode error with a user-facing message."""


def _capture_until_utterance(config: ListenConfig) -> bytes:
    """Capture PCM16 mono from the microphone until VAD detects an utterance.

    Returns raw PCM16 bytes covering the first detected utterance. Returns an
    empty byte string if no utterance is detected before *max_record_seconds*.

    Raises:
        ListenError: if the microphone or audio subsystem cannot be opened.
    """
    vad = WebrtcVadBackend(
        aggressiveness=config.vad_aggressiveness,
        sample_rate=DEFAULT_SAMPLE_RATE,
        silence_ms=config.vad_silence_ms,
        max_utterance_ms=config.vad_max_utterance_ms,
    )

    buffer = bytearray()
    deadline = time.monotonic() + config.max_record_seconds

    print("gravando... fale agora (VAD deteta a sua fala)", file=sys.stderr)

    try:
        import sounddevice as sd  # type: ignore[import-not-found]  # noqa: PLC0415 - lazy import per CLAUDE.md

        with sd.InputStream(
            samplerate=DEFAULT_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_BYTES,
        ) as stream:
            while time.monotonic() < deadline:
                data, _overflowed = stream.read(FRAME_BYTES)
                buffer.extend(bytes(data))

                # Only run VAD over complete frames.
                usable = len(buffer) - (len(buffer) % FRAME_BYTES)
                if usable < FRAME_BYTES:
                    continue

                pcm = bytes(buffer[:usable])
                utterances = list(vad.segment(pcm))
                if utterances:
                    start, end = utterances[0]
                    return pcm[start:end]
    except ImportError as exc:
        raise ListenError(
            "sounddevice is not installed — microphone capture unavailable",
        ) from exc
    except OSError as exc:
        raise ListenError(f"could not open microphone: {exc}") from exc

    return bytes(buffer)


def _capture_fixed_seconds(config: ListenConfig) -> bytes:
    """Capture PCM16 mono from the microphone for a fixed number of seconds.

    Falls back to time-based capture when VAD segmentation is unreliable
    (e.g. background noise, quiet voice, no speech detected).

    Returns raw PCM16 bytes covering the full recording duration.
    """
    total_frames = int(DEFAULT_SAMPLE_RATE * config.fixed_seconds)
    buffer = bytearray()

    print(f"gravando por {config.fixed_seconds:.0f}s — fale agora...", file=sys.stderr)

    try:
        import sounddevice as sd  # noqa: PLC0415 - lazy import per CLAUDE.md

        with sd.InputStream(
            samplerate=DEFAULT_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_BYTES,
        ) as stream:
            while len(buffer) < total_frames:
                remaining = total_frames - len(buffer)
                block = min(FRAME_BYTES, remaining)
                data, _overflowed = stream.read(block)
                buffer.extend(bytes(data))
    except ImportError as exc:
        raise ListenError(
            "sounddevice is not installed — microphone capture unavailable",
        ) from exc
    except OSError as exc:
        raise ListenError(f"could not open microphone: {exc}") from exc

    print("gravação terminada.", file=sys.stderr)
    return bytes(buffer)


def _transcribe_pcm(pcm: bytes, config: ListenConfig) -> str:
    """Wrap PCM16 in a WAV container and transcribe via whisper.cpp.

    Raises:
        BackendNotAvailableError: if whisper.cpp is not on PATH.
        BackendExecutionError: if transcription fails.
    """
    wav = pcm16_to_wav(pcm, sample_rate=DEFAULT_SAMPLE_RATE)
    stt = WhisperCppBackend(
        model=config.stt_model,
        language=config.stt_language,
    )
    return stt.transcribe(wav)


def run(config: ListenConfig | None = None) -> int:
    """Run listen mode: capture, transcribe, print transcript to stdout.

    Returns a process exit code: 0 on success (including "no speech"),
    2 on configuration or dependency error.
    """
    if config is None:
        config = load_config()

    if not config.stt_model:
        print(
            "error: VOICEVISION_STT_MODEL is not set",
            file=sys.stderr,
        )
        print(
            "  set it to the path of a whisper.cpp model file (e.g. whisper-base.bin)",
            file=sys.stderr,
        )
        return 2

    try:
        if config.fixed_seconds > 0:
            pcm = _capture_fixed_seconds(config)
        else:
            pcm = _capture_until_utterance(config)
    except ListenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("  install: pip install voicevision[audio]", file=sys.stderr)
        return 2

    if not pcm:
        print("no speech detected", file=sys.stderr)
        return 0

    try:
        transcript = _transcribe_pcm(pcm, config)
    except BackendNotAvailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(f"  fix: {exc.install_hint}", file=sys.stderr)
        return 2
    except BackendExecutionError as exc:
        print(f"error: transcription failed: {exc}", file=sys.stderr)
        return 2

    if transcript:
        print(transcript)
    else:
        print("no speech detected", file=sys.stderr)

    return 0


def main() -> None:
    """CLI entry point for ``voicevision-listen``."""
    parser = argparse.ArgumentParser(
        description="voicevision listen mode: microphone → STT → text on stdout",
    )
    parser.add_argument(
        "--model",
        help="Path to whisper.cpp model (overrides VOICEVISION_STT_MODEL)",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="STT language code (default: en)",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=0.0,
        help="Record for a fixed number of seconds instead of VAD detection "
        "(e.g. --seconds 5). Disables VAD segmentation.",
    )
    args = parser.parse_args()

    config = load_config()
    if args.model:
        config = replace(config, stt_model=args.model)
    config = replace(config, stt_language=args.language)
    if args.seconds > 0:
        config = replace(config, fixed_seconds=args.seconds)

    sys.exit(run(config))


if __name__ == "__main__":
    main()
