"""Listen mode: microphone → VAD → STT → text on stdout.

A minimal, listen-only entry point for voicevision. Captures audio from the
microphone, segments it with WebRTC VAD, transcribes each utterance via
whisper.cpp, and prints the transcript to stdout. No LLM, no TTS — just
speech in, text out.

Designed to be invoked by an editor keybind (e.g. OpenCode) so the user can
speak instead of typing. This module itself never touches the network; audio
is captured and transcribed locally. The separate ``voicevision.server`` module
offers an opt-in localhost HTTP interface for other processes.

All heavy dependencies (sounddevice, webrtcvad, whisper.cpp) are probed
lazily so `import voicevision.listen` stays cheap and fails with a clear
install hint only when capture is actually attempted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from voicevision.audio import pcm16_to_wav
from voicevision.backends.vad import WebrtcVadBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.core.hotwords import HotwordConfig, load_hotwords, wake_words_detected
from voicevision.errors import BackendExecutionError, BackendNotAvailableError
from voicevision.history import HistoryEntry, HistoryStore, default_history_path

#: whisper.cpp requires 16 kHz mono PCM16; VAD operates at the same rate.
DEFAULT_SAMPLE_RATE: Final = 16_000
#: VAD frame size: 30 ms at 16 kHz mono PCM16 = 960 bytes.
FRAME_BYTES: Final = (DEFAULT_SAMPLE_RATE * 30 // 1000) * 2


class PreRollBuffer:
    """Fixed-size circular buffer of PCM16 audio bytes.

    Holds the last *max_bytes* of audio so that, when a wake word is detected,
    the audio leading up to it (including the start of the utterance) is not
    lost. 16 kHz mono PCM16 is 32 KB/s, so a 10 s buffer is ~320 KB.

    A *max_bytes* of 0 means unlimited (no pre-roll limit, pass-through).

    Not thread-safe: a single caller pushes and reads.
    """

    def __init__(self, max_bytes: int) -> None:
        if max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")
        self._unbounded = max_bytes == 0
        self._max_bytes = max_bytes or (1 << 62)  # 0 means unlimited
        self._buf = bytearray(self._max_bytes) if not self._unbounded else bytearray()
        self._write = 0
        self._filled = 0

    def push(self, data: bytes) -> None:
        """Append *data* to the buffer, overwriting the oldest bytes if full."""
        n = len(data)
        if n == 0:
            return
        if self._unbounded:
            self._buf.extend(data)
            self._filled = len(self._buf)
            self._write = len(self._buf)
            return
        if n >= self._max_bytes:
            # Data is larger than the whole buffer: keep only the tail.
            self._buf[:] = data[-self._max_bytes :]
            self._write = 0
            self._filled = self._max_bytes
            return
        if self._write + n <= self._max_bytes:
            self._buf[self._write : self._write + n] = data
            self._write += n
        else:
            # Wraps around the end of the buffer.
            first = self._max_bytes - self._write
            self._buf[self._write :] = data[:first]
            self._buf[: n - first] = data[first:]
            self._write = n - first
        self._filled = min(self._filled + n, self._max_bytes)

    def get(self) -> bytes:
        """Return all buffered audio in chronological order."""
        if self._filled == 0:
            return b""
        if self._unbounded:
            return bytes(self._buf)
        if self._filled == self._max_bytes and self._write == 0:
            return bytes(self._buf)
        # Buffer wrapped: tail + head.
        start = (self._write - self._filled) % self._max_bytes
        end = self._write
        if start < end:
            return bytes(self._buf[start:end])
        return bytes(self._buf[start:]) + bytes(self._buf[:end])

    def clear(self) -> None:
        """Empty the buffer."""
        self._write = 0
        self._filled = 0
        if not self._unbounded:
            self._buf = bytearray(self._max_bytes)
        else:
            self._buf = bytearray()

    def size(self) -> int:
        """Return the number of bytes currently buffered."""
        return self._filled


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
    hotwords: HotwordConfig = field(default_factory=HotwordConfig)
    pre_roll_seconds: float = 0.0
    json_output: bool = False
    quiet: bool = False
    history_enabled: bool = False
    history_file: str = ""
    continuous: bool = False
    mute_tts: bool = False


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


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var (0/false/no/off disable; anything else enables)."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _normalize_text(text: str) -> str:
    """Normalize text for wake word matching.

    Lowercases, decomposes accented characters (NFD), strips combining marks,
    and collapses whitespace. This makes "Olá Ambrósio", "OLÁ AMBRÓSIO" and
    "ola ambrosio" all match the same wake word.
    """
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in text if c.isalnum() or c.isspace())
    return " ".join(stripped.split())


def _wake_word_detected(transcript: str, config: ListenConfig) -> tuple[bool, str | None]:
    """Return (True, matched_word) if any configured wake word is in *transcript*.

    Both sides are normalized so accent/case/punctuation differences do not
    cause false negatives.
    """
    return wake_words_detected(transcript, config.hotwords)


def _strip_wake_word(transcript: str, wake_word: str) -> str:
    """Return *transcript* with the first occurrence of *wake_word* removed.

    Matching is normalized; the returned text is also normalized (lowercase,
    no accents, collapsed whitespace). This matches the historical behaviour
    used for JSON output.
    """
    if not wake_word:
        return transcript
    norm_text = _normalize_text(transcript)
    norm_wake = _normalize_text(wake_word)
    idx = norm_text.find(norm_wake)
    if idx < 0:
        return _normalize_text(transcript)
    return norm_text[idx + len(norm_wake) :].strip()


def _pre_roll_bytes(seconds: float) -> int:
    """Return the number of PCM16 bytes for *seconds* of 16 kHz mono audio."""
    return int(seconds * DEFAULT_SAMPLE_RATE * 2)


def load_config() -> ListenConfig:
    """Build a :class:`ListenConfig` from environment variables.

    Reads ``VOICEVISION_STT_MODEL``, ``VOICEVISION_STT_LANGUAGE``,
    ``VOICEVISION_VAD_AGGRESSIVENESS``, ``VOICEVISION_VAD_SILENCE_MS``,
    ``VOICEVISION_VAD_MAX_UTTERANCE_MS``,
    ``VOICEVISION_MAX_RECORD_SECONDS``, ``VOICEVISION_WAKE_WORD`` (legacy),
    ``VOICEVISION_HOTWORDS``, ``VOICEVISION_PRE_ROLL_SECONDS`` and
    ``VOICEVISION_MUTE_TTS``.
    """
    hotwords = load_hotwords()
    # Backward compatibility: VOICEVISION_WAKE_WORD overrides the first word
    if legacy_wake := os.environ.get("VOICEVISION_WAKE_WORD"):
        hotwords = HotwordConfig(
            words=[legacy_wake] + hotwords.words[1:],
            threshold=hotwords.threshold,
        )
    return ListenConfig(
        stt_model=os.environ.get("VOICEVISION_STT_MODEL", ""),
        stt_language=os.environ.get("VOICEVISION_STT_LANGUAGE", "en"),
        vad_aggressiveness=_env_int("VOICEVISION_VAD_AGGRESSIVENESS", 2),
        vad_silence_ms=_env_int("VOICEVISION_VAD_SILENCE_MS", 500),
        vad_max_utterance_ms=_env_int("VOICEVISION_VAD_MAX_UTTERANCE_MS", 30_000),
        max_record_seconds=_env_float("VOICEVISION_MAX_RECORD_SECONDS", 60.0),
        fixed_seconds=_env_float("VOICEVISION_FIXED_SECONDS", 0.0),
        hotwords=hotwords,
        pre_roll_seconds=_env_float("VOICEVISION_PRE_ROLL_SECONDS", 0.0),
        quiet=_env_int("VOICEVISION_QUIET", 0) == 1,
        history_enabled=_env_bool("VOICEVISION_HISTORY_ENABLED", True),
        history_file=os.environ.get("VOICEVISION_HISTORY_FILE", ""),
        continuous=_env_bool("VOICEVISION_CONTINUOUS", False),
        mute_tts=_env_bool("VOICEVISION_MUTE_TTS", False),
    )


def _diag(config: ListenConfig, message: str) -> None:
    """Write a diagnostic message to stderr unless quiet mode is active.

    Only progress and outcome messages are routed through here. Fatal errors
    keep going to stderr unconditionally: suppressing them would leave callers
    with nothing but an exit code, which is not enough to tell a missing
    backend from a failed transcription.
    """
    if not config.quiet:
        print(message, file=sys.stderr)


def _record_history(
    config: ListenConfig,
    transcript: str,
    *,
    pcm_duration_seconds: float | None,
    transcription_ms: float | None,
    wake_word: str | None = None,
) -> None:
    """Append the transcript to the history file, best effort.

    A history failure must never fail dictation: the user already has the
    transcript on stdout, and losing the record is preferable to losing the
    session. The warning is suppressed in quiet mode like other diagnostics.
    """
    if not config.history_enabled or not transcript:
        return
    path = Path(config.history_file).expanduser() if config.history_file else default_history_path()
    entry = HistoryEntry.now(
        transcript,
        language=config.stt_language,
        audio_duration_seconds=pcm_duration_seconds,
        transcription_ms=transcription_ms,
        wake_word=wake_word,
    )
    try:
        HistoryStore(path).append(entry)
    except OSError as exc:
        _diag(config, f"warning: could not write history: {exc}")


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

    _diag(config, "gravando... fale agora (VAD deteta a sua fala)")

    try:
        import sounddevice as sd  # type: ignore[import-untyped]  # noqa: PLC0415 - lazy import per CLAUDE.md

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

    _diag(config, f"gravando por {config.fixed_seconds:.0f}s — fale agora...")

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

    _diag(config, "gravação terminada.")
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
    return stt.transcribe(wav, language=config.stt_language)


def _format_output(
    transcript: str,
    config: ListenConfig,
    *,
    pcm_duration_seconds: float | None = None,
    transcription_ms: float | None = None,
    wake_word_detected: bool | None = None,
) -> str:
    """Format output as plain text or JSON depending on config."""
    if not config.json_output:
        return transcript

    import time as _time

    result: dict[str, object] = {
        "transcript": transcript,
        "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%S"),
        "language": config.stt_language,
    }

    if pcm_duration_seconds is not None:
        result["audio_duration_seconds"] = pcm_duration_seconds

    if transcription_ms is not None:
        result["transcription_ms"] = transcription_ms

    if wake_word_detected is not None:
        result["wake_word_detected"] = wake_word_detected
        if config.hotwords.words:
            result["wake_word"] = config.hotwords.words[0]

    return json.dumps(result, ensure_ascii=False)


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

    if config.continuous and not config.hotwords.words:
        print(
            "error: --continuous requires a wake word (--wake-word or VOICEVISION_WAKE_WORD)",
            file=sys.stderr,
        )
        return 2

    if config.hotwords.words:
        if config.continuous:
            return _run_wake_word_continuous(config)
        return _run_wake_word(config)

    return _run_single_shot(config)


def _run_single_shot(config: ListenConfig) -> int:
    """Capture one utterance, transcribe it, print it, and record it."""
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
        _diag(config, "no speech detected")
        return 0

    pcm_duration_seconds = len(pcm) / (DEFAULT_SAMPLE_RATE * 2)
    start_time = time.monotonic()
    try:
        transcript = _transcribe_pcm(pcm, config)
    except BackendNotAvailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(f"  fix: {exc.install_hint}", file=sys.stderr)
        return 2
    except BackendExecutionError as exc:
        print(f"error: transcription failed: {exc}", file=sys.stderr)
        return 2
    transcription_ms = (time.monotonic() - start_time) * 1000

    if transcript:
        _record_history(
            config,
            transcript,
            pcm_duration_seconds=pcm_duration_seconds,
            transcription_ms=transcription_ms,
        )
        print(
            _format_output(
                transcript,
                config,
                pcm_duration_seconds=pcm_duration_seconds,
                transcription_ms=transcription_ms,
            )
        )
    else:
        _diag(config, "no speech detected")

    return 0


def _run_wake_word(config: ListenConfig) -> int:
    """Run listen mode with wake word detection.

    Captures and transcribes utterances in a loop until one contains any
    configured wake word. When detected, prints the transcript (with the wake
    word stripped) to stdout and returns 0. If no wake word is heard before
    *config.max_record_seconds*, returns 0 with no output.

    Returns:
        0 on wake word detected or timeout; 2 on configuration/dependency error.
    """
    words = ", ".join(config.hotwords.words)
    _diag(config, f"listening for wake word '{words}'...")

    deadline = time.monotonic() + config.max_record_seconds
    vad = WebrtcVadBackend(
        aggressiveness=config.vad_aggressiveness,
        sample_rate=DEFAULT_SAMPLE_RATE,
        silence_ms=config.vad_silence_ms,
        max_utterance_ms=config.vad_max_utterance_ms,
    )

    pre_roll = PreRollBuffer(_pre_roll_bytes(config.pre_roll_seconds))

    try:
        import sounddevice as sd  # noqa: PLC0415 - lazy import per CLAUDE.md

        with sd.InputStream(
            samplerate=DEFAULT_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_BYTES,
        ) as stream:
            while time.monotonic() < deadline:
                data, _overflowed = stream.read(FRAME_BYTES)
                pre_roll.push(bytes(data))

                pcm = pre_roll.get()
                usable = len(pcm) - (len(pcm) % FRAME_BYTES)
                if usable < FRAME_BYTES:
                    continue

                utterances = list(vad.segment(pcm[:usable]))
                if not utterances:
                    continue

                result = _transcribe_utterances(
                    pcm[:usable], utterances, config, _pre_roll_bytes(config.pre_roll_seconds)
                )
                if result is not None:
                    transcript_result, transcription_ms, matched_word = result
                    pcm_duration_seconds = len(pcm[:usable]) / (DEFAULT_SAMPLE_RATE * 2)
                    _record_history(
                        config,
                        transcript_result,
                        pcm_duration_seconds=pcm_duration_seconds,
                        transcription_ms=transcription_ms,
                        wake_word=matched_word,
                    )
                    print(
                        _format_output(
                            transcript_result,
                            config,
                            pcm_duration_seconds=pcm_duration_seconds,
                            transcription_ms=transcription_ms,
                            wake_word_detected=True,
                        )
                    )
                    return 0

    except ListenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("  install: pip install voicevision[audio]", file=sys.stderr)
        return 2

    _diag(config, "wake word not detected")
    return 0


#: Hard cap on the rolling buffer in continuous mode (seconds of audio).
#: The VAD runaway guard normally closes utterances long before this.
CONTINUOUS_BUFFER_SECONDS: Final = 60


def _run_wake_word_continuous(config: ListenConfig) -> int:
    """Keep listening and print every utterance that contains a wake word.

    Runs until ``Ctrl+C``. Unlike :func:`_run_wake_word`, this never exits
    after a detection, so it can back a resident assistant.

    The buffer is trimmed after each pass and the processed byte offset is
    tracked, which prevents re-transcribing an utterance while the VAD buffer
    keeps growing. The retained tail also acts as pre-roll for the next wake
    word.
    """
    words = ", ".join(config.hotwords.words)
    _diag(
        config,
        f"listening continuously for '{words}'... (Ctrl+C to stop)",
    )

    vad = WebrtcVadBackend(
        aggressiveness=config.vad_aggressiveness,
        sample_rate=DEFAULT_SAMPLE_RATE,
        silence_ms=config.vad_silence_ms,
        max_utterance_ms=config.vad_max_utterance_ms,
    )
    max_buffer_bytes = CONTINUOUS_BUFFER_SECONDS * DEFAULT_SAMPLE_RATE * 2
    buffer = bytearray()
    processed = 0

    try:
        import sounddevice as sd  # noqa: PLC0415 - lazy import per CLAUDE.md

        with sd.InputStream(
            samplerate=DEFAULT_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=FRAME_BYTES,
        ) as stream:
            while True:
                data, _overflowed = stream.read(FRAME_BYTES)
                buffer.extend(bytes(data))

                usable = len(buffer) - (len(buffer) % FRAME_BYTES)
                if usable >= FRAME_BYTES:
                    pcm = bytes(buffer[:usable])
                    for start, end in vad.segment(pcm):
                        if end <= processed:
                            continue
                        processed = end
                        result = _transcribe_utterances(pcm, [(start, end)], config)
                        if result is None:
                            continue
                        transcript_result, transcription_ms, matched_word = result
                        pcm_duration_seconds = (end - start) / (DEFAULT_SAMPLE_RATE * 2)
                        _record_history(
                            config,
                            transcript_result,
                            pcm_duration_seconds=pcm_duration_seconds,
                            transcription_ms=transcription_ms,
                            wake_word=matched_word,
                        )
                        print(
                            _format_output(
                                transcript_result,
                                config,
                                pcm_duration_seconds=pcm_duration_seconds,
                                transcription_ms=transcription_ms,
                                wake_word_detected=True,
                            )
                        )

                if processed:
                    del buffer[:processed]
                    processed = 0

                if len(buffer) > max_buffer_bytes:
                    del buffer[:-max_buffer_bytes]

    except KeyboardInterrupt:
        _diag(config, "stopped")
        return 0
    except ListenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("  install: pip install voicevision[audio]", file=sys.stderr)
        return 2


def _transcribe_utterances(
    pcm: bytes,
    utterances: list[tuple[int, int]],
    config: ListenConfig,
    pre_roll_bytes: int = 0,
) -> tuple[str, float, str] | None:
    """Transcribe each utterance and check for the wake word.

    When *pre_roll_bytes* > 0, the audio immediately preceding each utterance
    (up to *pre_roll_bytes*) is prepended so the wake word's lead-in is not
    lost to VAD segmentation.

    Returns a tuple of (remainder, transcription_ms, matched_word) if any wake
    word is detected in any utterance, or ``None`` if none matched.
    """
    start_time = time.monotonic()
    for start, end in utterances:
        pre_roll_start = max(0, start - pre_roll_bytes)
        utterance_pcm = pcm[pre_roll_start:end]
        try:
            transcript = _transcribe_pcm(utterance_pcm, config)
        except BackendNotAvailableError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(f"  fix: {exc.install_hint}", file=sys.stderr)
            raise SystemExit(2) from None
        except BackendExecutionError as exc:
            print(f"error: transcription failed: {exc}", file=sys.stderr)
            raise SystemExit(2) from None

        if not transcript.strip():
            continue

        detected, matched_word = _wake_word_detected(transcript, config)
        if detected and matched_word is not None:
            remainder = _strip_wake_word(transcript, matched_word)
            transcription_ms = (time.monotonic() - start_time) * 1000
            return (remainder if remainder else "wake word detected",
                    transcription_ms,
                    matched_word)

    return None


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
        help="STT language code (default: en). Use 'auto' for automatic detection.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=0.0,
        help="Record for a fixed number of seconds instead of VAD detection "
        "(e.g. --seconds 5). Disables VAD segmentation.",
    )
    parser.add_argument(
        "--wake-word",
        default="",
        help="Wake word to listen for (e.g. 'Olá Ambrósio'). Overrides "
        "the first word in VOICEVISION_HOTWORDS or the default. Empty disables "
        "wake word mode.",
    )
    parser.add_argument(
        "--hotwords-file",
        default="",
        help="Path to JSON file with wake words (overrides VOICEVISION_HOTWORDS). "
        "Format: {\"words\": [\"wake word 1\", \"wake word 2\"], \"threshold\": 0.5}",
    )
    parser.add_argument(
        "--pre-roll-seconds",
        type=float,
        default=0.0,
        help="Seconds of audio to prepend before each utterance when wake "
        "word mode is active (e.g. --pre-roll-seconds 2). Default: 0.",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        default=False,
        help="Keep listening and print every wake word utterance until Ctrl+C "
        "(requires --wake-word)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output transcript as JSON instead of plain text",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress progress and outcome messages on stderr "
        "(fatal errors are still reported)",
    )
    parser.add_argument(
        "--mute",
        action="store_true",
        default=False,
        help="Run the full pipeline but suppress TTS output "
        "(useful for testing or chaining with another TTS)",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        default=False,
        help="Do not append this transcript to the history file",
    )
    parser.add_argument(
        "--history-file",
        default="",
        help="History file path (default: ~/.voicevision/history.jsonl)",
    )
    args = parser.parse_args()

    config = load_config()
    if args.model:
        config = replace(config, stt_model=args.model)
    config = replace(config, stt_language=args.language)
    if args.seconds > 0:
        config = replace(config, fixed_seconds=args.seconds)
    # Handle hotwords file override
    if args.hotwords_file:
        config = replace(config, hotwords=load_hotwords(path=Path(args.hotwords_file)))
    # Handle wake-word: replace first word in the list
    if args.wake_word:
        new_hotwords = HotwordConfig(
            words=[args.wake_word] + config.hotwords.words[1:],
            threshold=config.hotwords.threshold,
        )
        config = replace(config, hotwords=new_hotwords)
    if args.pre_roll_seconds > 0:
        config = replace(config, pre_roll_seconds=args.pre_roll_seconds)
    if args.json:
        config = replace(config, json_output=True)
    if args.quiet:
        config = replace(config, quiet=True)
    if args.mute:
        config = replace(config, mute_tts=True)
    if args.no_history:
        config = replace(config, history_enabled=False)
    if args.history_file:
        config = replace(config, history_file=args.history_file)
    if args.continuous:
        config = replace(config, continuous=True)

    sys.exit(run(config))


if __name__ == "__main__":
    main()
