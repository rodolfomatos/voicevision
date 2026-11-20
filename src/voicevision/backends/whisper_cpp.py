"""Speech to text via the whisper.cpp CLI (ADR-001).

whisper.cpp is a one-shot program: it reads a WAV file from stdin, prints a
transcript, and exits. That matches SubprocessBackend's semantics exactly — see
that module's docstring for why it spawns per call rather than keeping a child
warm.

Implements STTProvider protocol (M1) with streaming support via chunked processing
(T088) and, when the installed binary advertises it, true streaming via a
persistent child process (T091).
"""

from __future__ import annotations

import io
import queue
import re
import shutil
import subprocess
import threading
import wave
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from typing import ClassVar, Final

from voicevision.audio import pcm16_to_wav, require_whisper_format
from voicevision.backends.subprocess_backend import SubprocessBackend
from voicevision.core.cancellation import CancellationToken
from voicevision.core.protocols import (
    ProviderCapabilities,
    ProviderLifecycle,
    STTChunk,
    VADProvider,
)
from voicevision.errors import ProviderRuntimeError
from voicevision.text import extract_sentences

#: whisper.cpp prefixes each segment with `[00:00:00.000 --> 00:00:02.000]`.
#: `-nt` suppresses these, but forks differ, so strip defensively rather than
#: trust the flag was honoured.
_TIMESTAMP = re.compile(r"^\s*\[[^\]]*-->[^\]]*\]\s*", re.MULTILINE)

#: Some builds bracket non-speech markers such as `[BLANK_AUDIO]` or `(music)`.
_BRACKETED = re.compile(r"\[[A-Z_]{3,}\]")

#: Backends that write a transcript file instead of stdout put this on stdout.
_FILE_WRITTEN = re.compile(r"^\s*.*\.txt\s*$", re.MULTILINE)

#: whisper.cpp word timestamps look like `[00:00:01.200 --> 00:00:01.600]  hello`.
_WORD_TIMESTAMP = re.compile(
    r"\[(\d+):(\d+):(\d+)\.(\d+)\s*-->\s*(\d+):(\d+):(\d+)\.(\d+)\]\s*(\S+)"
)

#: Supported latency targets, in milliseconds. Anything else is a config error:
#: silently accepting 37 ms would promise a latency we cannot deliver.
LATENCY_TARGETS: Final = (50, 100, 200)

#: (chunk_size_ms, overlap_ms) used when a latency target is given but the
#: caller does not override the chunk parameters explicitly.
LATENCY_CHUNK_MS: Final[dict[int, tuple[int, int]]] = {
    50: (500, 150),
    100: (1000, 300),
    200: (2000, 600),
}

#: Frame size used when an external VAD is supplied (30 ms @ 16 kHz, PCM16).
_VAD_FRAME_BYTES: Final = 960


@dataclass(frozen=True)
class WordTiming:
    """One word from whisper.cpp's optional word-timestamp output."""

    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class StreamingConfig:
    """Validated options for :meth:`WhisperCppBackend.transcribe_stream`.

    ``latency_target_ms`` is one of :data:`LATENCY_TARGETS`. It drives the
    chunk size (and, on binaries that support it, whisper.cpp's ``-t`` flag).
    """

    latency_target_ms: int = 100
    chunk_size_ms: int = 1500
    overlap_ms: int = 500
    use_vad: bool = False
    detect_language: bool = False
    word_timestamps: bool = False

    def __post_init__(self) -> None:
        if self.latency_target_ms not in LATENCY_TARGETS:
            raise ValueError(
                f"latency_target_ms must be one of {LATENCY_TARGETS}, "
                f"got {self.latency_target_ms}"
            )
        if self.chunk_size_ms <= 0:
            raise ValueError("chunk_size_ms must be positive")
        if self.overlap_ms < 0 or self.overlap_ms >= self.chunk_size_ms:
            raise ValueError("overlap_ms must be >= 0 and < chunk_size_ms")

    @property
    def bytes_per_ms(self) -> int:
        return DEFAULT_SAMPLE_RATE // 1000 * 2  # 16-bit mono

    @property
    def chunk_bytes(self) -> int:
        return self.chunk_size_ms * self.bytes_per_ms

    @property
    def overlap_bytes(self) -> int:
        return self.overlap_ms * self.bytes_per_ms

    @classmethod
    def from_kwargs(cls, kwargs: Mapping[str, object]) -> StreamingConfig:
        """Build a config from the free-form kwargs accepted by transcribe_stream.

        A lower latency target means smaller chunks; an explicit chunk_size_ms
        always wins. This keeps the 50/100/200 ms targets meaningful on binaries
        without native streaming, where chunk size *is* the latency.
        """
        latency = _kwarg_int(kwargs, "latency_target_ms", 100)
        chunk_default, overlap_default = LATENCY_CHUNK_MS.get(latency, (1500, 500))
        return cls(
            latency_target_ms=latency,
            chunk_size_ms=_kwarg_int(kwargs, "chunk_size_ms", chunk_default),
            overlap_ms=_kwarg_int(kwargs, "overlap_ms", overlap_default),
            use_vad=_kwarg_bool(kwargs, "use_vad", False),
            detect_language=_kwarg_bool(kwargs, "detect_language", False),
            word_timestamps=_kwarg_bool(kwargs, "word_timestamps", False),
        )


def _kwarg_int(kwargs: Mapping[str, object], key: str, default: int) -> int:
    value = kwargs.get(key, default)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _kwarg_bool(kwargs: Mapping[str, object], key: str, default: bool) -> bool:
    value = kwargs.get(key, default)
    if isinstance(value, bool):
        return value
    return default


def _hms_to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(millis)
    )


def _supports_true_streaming(binary: str) -> bool:
    """Return True when the binary advertises a real-time streaming flag.

    whisper.cpp proper is a one-shot CLI; some forks expose a streaming mode.
    We probe ``--help`` once per unique binary and cache the answer. A binary
    that cannot be run is simply not capable — it will fail later with the
    usual NotAvailable error if the caller tries to use it.
    """
    cached = _TRUE_STREAMING_CACHE.get(binary)
    if cached is not None:
        return cached
    try:
        result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        help_text = (result.stdout or "") + (result.stderr or "")
        supported = bool(
            re.search(r"-\s*t,?\s+.*stream|stream.*-\s*t", help_text, re.IGNORECASE)
        )
    except (OSError, subprocess.SubprocessError):
        supported = False
    _TRUE_STREAMING_CACHE[binary] = supported
    return supported


_TRUE_STREAMING_CACHE: dict[str, bool] = {}


class WhisperCppBackend(SubprocessBackend):
    """Transcribe 16 kHz mono PCM16 WAV using whisper.cpp.

    Implements STTProvider protocol with streaming support via chunked processing.
    The model path is supplied by the caller; this class never downloads
    anything.
    """

    #: whisper.cpp renamed `main` to `whisper-cli`; older builds and forks still
    #: ship `main`, so both are probed.
    executable: ClassVar[str] = "whisper-cli"
    alternate_executables: ClassVar[tuple[str, ...]] = ("main",)

    install_hint: ClassVar[str] = (
        "Build whisper.cpp: git clone https://github.com/gguerganov/whisper.cpp "
        "&& cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build "
        "--target whisper-cli"
    )

    def __init__(
        self,
        model: str,
        *,
        language: str = "en",
        binary: str | None = None,
        timeout: float | None = None,
        extra_args: list[str] | None = None,
    ) -> None:
        if not model:
            raise ValueError("model path is required — this backend does not download models")
        self._model = model
        self._language = language
        self._extra_args = list(extra_args or [])

        chosen = binary or self._resolve_binary()
        self._binary = chosen
        super().__init__(
            self._build_argv(chosen),
            timeout=timeout,
            name="whispercpp",
        )

    @staticmethod
    def _resolve_binary() -> str:
        for candidate in (WhisperCppBackend.executable, *WhisperCppBackend.alternate_executables):
            if shutil.which(candidate):
                return candidate
        # Not installed. Use the canonical name so the argv is at least
        # recognisable; available() reports the truth.
        return WhisperCppBackend.executable

    def _build_argv(self, binary: str) -> list[str]:
        return [
            binary,
            "-m",
            self._model,
            "-f",
            "-",  # read WAV from stdin
            "-l",
            self._language,
            "-otxt",
            "-of",
            "-",  # write the transcript to stdout
            "-nt",  # no timestamps
            "-np",  # no progress output
            *self._extra_args,
        ]

    @classmethod
    def available(cls) -> bool:
        candidates = (cls.executable, *cls.alternate_executables)
        return any(shutil.which(c) for c in candidates)

    # install_hint is a class attribute. The protocol expects a classmethod,
    # but @runtime_checkable only validates instance methods. Class attribute works.

    # -- STTProvider protocol --------------------------------------------------

    def transcribe(
        self,
        audio: bytes,
        *,
        language: str | None = None,
        token: CancellationToken | None = None,
        **kwargs: object,
    ) -> str:
        """Transcribe a WAV file.

        Args:
            audio: 16 kHz mono PCM16 WAV bytes.
            language: Language code (e.g., 'en', 'pt') or "auto" for detection.
                If None, uses the language from constructor.
            token: Optional cancellation token.
            **kwargs: Ignored; per-call overrides belong on constructor.

        Returns:
            The transcript. Empty string when the audio contains no speech.

        Raises:
            AudioFormatError: if the audio is not 16 kHz mono PCM16.
            ProviderUnavailableError: if whisper.cpp is not installed.
            ProviderRuntimeError: if whisper.cpp fails.
        """
        # Check cancellation before spawning
        if token is not None:
            token.throw_if_cancelled()

        # Validate before spawning. A format problem is the caller's bug and
        # naming it precisely is more useful than whatever whisper.cpp makes of
        # it. Never resample here — see voicevision.audio.
        require_whisper_format(audio)

        # Auto-detect language if requested
        if language == "auto":
            language = self.detect_language(audio, token=token)

        # If language differs from constructor, rebuild argv
        if language and language != self._language:
            original_language = self._language
            self._language = language
            self._argv = self._build_argv(self._binary or self._resolve_binary())
            try:
                raw = self.run(audio).decode("utf-8", errors="replace")
            finally:
                self._language = original_language
                self._argv = self._build_argv(self._binary or self._resolve_binary())
        else:
            raw = self.run(audio).decode("utf-8", errors="replace")
        return self.parse_transcript(raw)

    def _extract_chunk_params(
        self, kwargs: dict[str, object]
    ) -> tuple[int, int, int, int]:
        """Extract chunk parameters and convert to bytes."""
        chunk_size_ms_raw: int = kwargs.get("chunk_size_ms", 1500)  # type: ignore[assignment]
        overlap_ms_raw: int = kwargs.get("overlap_ms", 500)  # type: ignore[assignment]
        chunk_size_ms = int(chunk_size_ms_raw)
        overlap_ms = int(overlap_ms_raw)

        if chunk_size_ms <= overlap_ms:
            raise ValueError("chunk_size_ms must be greater than overlap_ms")

        # Convert ms to bytes (16kHz, 16-bit mono)
        samples_per_ms = self._sample_rate // 1000
        bytes_per_ms = samples_per_ms * 2  # 16-bit = 2 bytes
        chunk_bytes = chunk_size_ms * (samples_per_ms * 2)
        overlap_bytes = overlap_ms * bytes_per_ms
        return chunk_size_ms, overlap_ms, chunk_bytes, overlap_bytes

    def _transcribe_chunk(
        self,
        buf: bytes,
        lang: str | None,
        token: CancellationToken | None,
    ) -> tuple[str, str | None]:
        """Transcribe a single chunk and return (transcript, detected_language)."""
        if not buf:
            return "", None

        detected_lang = None
        lang = lang
        if lang is None:
            detected_lang = self.detect_language(buf)
            lang = detected_lang

        transcript = self.transcribe(buf, language=lang)
        return transcript, detected_lang

    def _process_transcript_chunk(
        self,
        transcript: str,
        accumulated_text: str,
        language: str | None,
        detected_language: str | None,
        timings: list[WordTiming] | None = None,
    ) -> tuple[str, list[STTChunk]]:
        """Process transcript chunk and return complete sentences as partial results."""
        combined = accumulated_text + transcript
        sentences = extract_sentences(combined)

        chunks: list[STTChunk] = []
        new_accumulated = accumulated_text
        start_ms = timings[0].start_ms if timings else None
        end_ms = timings[-1].end_ms if timings else None

        # Emit complete sentences as partial results
        for sentence in sentences[:-1]:  # All but last (might be incomplete)
            if sentence != accumulated_text:
                chunks.append(
                    STTChunk(
                        text=sentence,
                        is_final=False,
                        language=language or detected_language,
                        start_ms=start_ms,
                        end_ms=end_ms,
                    )
                )
                accumulated_text = sentence

        # Keep incomplete last sentence for next iteration
        new_accumulated = sentences[-1] if sentences else ""

        return new_accumulated, chunks

    # -- streaming (T088 + T091) -----------------------------------------------

    def supports_true_streaming(self) -> bool:
        """Whether the installed whisper.cpp binary advertises streaming mode."""
        binary = self._binary or self._resolve_binary()
        return _supports_true_streaming(binary)

    @staticmethod
    def _as_pcm_chunks(
        audio_chunks: Generator[bytes, None, None],
    ) -> Generator[bytes, None, None]:
        """Normalize input to raw PCM16, accepting WAV or raw PCM producers.

        T088 callers fed complete WAV files; the WebSocket streaming endpoint
        feeds raw PCM16 slices. Buffering, VAD and language probing all need raw
        PCM, so convert once at the boundary and wrap into WAV only when the
        one-shot CLI actually needs a file.
        """
        for chunk in audio_chunks:
            if not chunk:
                continue
            if chunk[:4] == b"RIFF" and chunk[8:12] == b"WAVE":
                require_whisper_format(chunk)
                with wave.open(io.BytesIO(chunk), "rb") as wav:
                    yield wav.readframes(wav.getnframes())
            else:
                yield chunk

    @staticmethod
    def _filter_vad(
        audio_chunks: Generator[bytes, None, None],
        vad: VADProvider,
        token: CancellationToken | None,
    ) -> Generator[bytes, None, None]:
        """Keep only speech frames, using the caller's VAD as the single gate.

        This is the "no double VAD" contract: when a VAD is supplied we do not
        run any internal silence detection, and the STT buffer only ever sees
        frames the caller's VAD accepted.
        """
        remainder = b""
        for chunk in audio_chunks:
            if token is not None:
                token.throw_if_cancelled()
            data = remainder + chunk
            frame_count = len(data) // _VAD_FRAME_BYTES
            for index in range(frame_count):
                frame = data[index * _VAD_FRAME_BYTES : (index + 1) * _VAD_FRAME_BYTES]
                if vad.process_frame(frame, token=token):
                    yield frame
            remainder = data[frame_count * _VAD_FRAME_BYTES :]
        # A trailing partial frame is < 30ms and cannot be classified reliably.

    def _detect_language_from_start(
        self,
        audio_chunks: Generator[bytes, None, None],
        config: StreamingConfig,
        token: CancellationToken | None,
    ) -> tuple[str, Generator[bytes, None, None]]:
        """Detect language from the first 1-2 s, then replay those chunks."""
        # The latency target may imply a sub-second chunk; language detection
        # still needs a stable 1-2 s window, so clamp independently of it.
        probe_target = min(max(config.chunk_bytes, 32_000), 64_000)
        probe = bytearray()
        for chunk in audio_chunks:
            probe.extend(chunk)
            if len(probe) >= probe_target:
                break
        if not probe:
            raise ProviderRuntimeError(
                "whispercpp", "stt", "no audio available for language detection"
            )
        detected = self.detect_language(pcm16_to_wav(bytes(probe)), token=token)

        def replay() -> Generator[bytes, None, None]:
            yield bytes(probe)
            yield from audio_chunks

        return detected, replay()

    def transcribe_stream(
        self,
        audio_chunks: Generator[bytes, None, None],
        *,
        language: str | None = None,
        token: CancellationToken | None = None,
        **kwargs: object,
    ) -> Generator[STTChunk, None, None]:
        """Transcribe an audio stream, emitting partial and final results.

        Two modes are supported:

        * **chunked** (always available): buffer audio, transcribe fixed-size
          chunks with overlap, and use sentence boundaries for partials.
        * **true streaming** (only when the binary advertises ``-t`` support):
          keep one child alive, feed it PCM16 on stdin and yield transcripts as
          they appear on stdout.

        Args:
            audio_chunks: PCM16 mono 16 kHz audio chunks.
            language: Language code, ``"auto"`` to detect from the first 1-2 s,
                or None to use the constructor language.
            token: Optional cancellation token.
            **kwargs: latency_target_ms (50/100/200), chunk_size_ms, overlap_ms,
                use_true_streaming, use_vad (requires ``vad``), detect_language,
                word_timestamps, and ``vad`` (a VADProvider).

        Yields:
            STTChunk objects; partials have is_final=False and a final result
            is emitted last. With word_timestamps=True, partials carry
            start_ms/end_ms from whisper.cpp's word-timestamp output.
        """
        config = StreamingConfig.from_kwargs(kwargs)
        chunks = self._as_pcm_chunks(audio_chunks)

        if config.use_vad:
            vad = kwargs.get("vad")
            if not isinstance(vad, VADProvider):
                raise ValueError("use_vad=True requires a 'vad' VADProvider in kwargs")
            chunks = self._filter_vad(chunks, vad, token)

        if language == "auto" or config.detect_language:
            language, chunks = self._detect_language_from_start(chunks, config, token)
        elif language is None:
            # The docstring promises the constructor language; never fall into
            # the per-chunk detect_language path by accident.
            language = self._language

        use_true_streaming = _kwarg_bool(kwargs, "use_true_streaming", True)
        if use_true_streaming and self.supports_true_streaming():
            yield from self._transcribe_stream_true(
                chunks, language=language, token=token, config=config
            )
        else:
            yield from self._transcribe_stream_chunked(
                chunks, language=language, token=token, config=config
            )

    def _transcribe_stream_chunked(
        self,
        audio_chunks: Generator[bytes, None, None],
        *,
        language: str | None,
        token: CancellationToken | None,
        config: StreamingConfig,
    ) -> Generator[STTChunk, None, None]:
        """Chunked processing with overlap — the reliable fallback path."""
        chunk_bytes = config.chunk_bytes
        overlap_bytes = config.overlap_bytes

        audio_buffer = bytearray()
        accumulated_text = ""
        combined = ""

        for chunk in audio_chunks:
            if token is not None:
                token.throw_if_cancelled()
            audio_buffer.extend(chunk)

            while len(audio_buffer) >= chunk_bytes:
                process_chunk = bytes(audio_buffer[:chunk_bytes])
                audio_buffer = audio_buffer[chunk_bytes - overlap_bytes :]

                transcript, timings = self._transcribe_for_chunk(
                    process_chunk, language, token, config
                )
                accumulated_text, yielded = self._process_transcript_chunk(
                    transcript, accumulated_text, language, None, timings
                )
                yield from yielded

        if audio_buffer:
            transcript, timings = self._transcribe_for_chunk(
                bytes(audio_buffer), language, token, config
            )
            combined = accumulated_text + transcript
            sentences = extract_sentences(combined)
            start_ms = timings[0].start_ms if timings else None
            end_ms = timings[-1].end_ms if timings else None
            for sentence in sentences[:-1]:
                if sentence != accumulated_text:
                    yield STTChunk(
                        text=sentence,
                        is_final=False,
                        language=language,
                        start_ms=start_ms,
                        end_ms=end_ms,
                    )
                    accumulated_text = sentence
            accumulated_text = sentences[-1] if sentences else ""

        final_text = accumulated_text or combined
        if final_text.strip():
            yield STTChunk(text=final_text, is_final=True, language=language)

    def _transcribe_for_chunk(
        self,
        buf: bytes,
        lang: str | None,
        token: CancellationToken | None,
        config: StreamingConfig,
    ) -> tuple[str, list[WordTiming]]:
        """Transcribe one chunk, optionally capturing word-level timings."""
        if not buf:
            return "", []
        wav = pcm16_to_wav(buf)
        if not config.word_timestamps:
            transcript, _detected = self._transcribe_chunk(wav, lang, token)
            return transcript, []
        transcript, _detected, raw = self._transcribe_chunk_timed(wav, lang, token)
        return transcript, self.parse_word_timestamps(raw)

    def _transcribe_chunk_timed(
        self,
        buf: bytes,
        lang: str | None,
        token: CancellationToken | None,
    ) -> tuple[str, str | None, str]:
        """Like _transcribe_chunk but keeps the raw output for word timestamps."""
        if token is not None:
            token.throw_if_cancelled()
        detected_lang = None
        effective = lang
        if effective is None:
            detected_lang = self.detect_language(buf)
            effective = detected_lang

        original_language = self._language
        original_argv = self._argv
        if effective and effective != original_language:
            self._language = effective
            self._argv = self._build_argv(self._binary or self._resolve_binary())
        if "-wt" not in self._argv:
            self._argv = [*self._argv, "-wt"]
        try:
            raw = self.run(buf).decode("utf-8", errors="replace")
        finally:
            self._language = original_language
            self._argv = original_argv
        return self.parse_transcript(raw), detected_lang, raw

    def _transcribe_stream_true(  # noqa: C901 - linear I/O loop with cleanup guard
        self,
        audio_chunks: Generator[bytes, None, None],
        *,
        language: str | None,
        token: CancellationToken | None,
        config: StreamingConfig,
    ) -> Generator[STTChunk, None, None]:
        """Persistent-child streaming: feed stdin, drain stdout via a queue.

        The reader thread puts lines on a queue rather than yielding from a
        thread (a generator cannot be consumed by ``Thread(target=...)``).
        stderr goes to DEVNULL so a chatty fork cannot deadlock the child.
        """
        if token is not None:
            token.throw_if_cancelled()

        binary = self._binary or self._resolve_binary()
        argv = [
            binary,
            "-m",
            self._model,
            "-f",
            "-",
            "-l",
            language or self._language,
            "-t",
            str(config.latency_target_ms),
            "-otxt",
            "-of",
            "-",
            "-nt",
            "-np",
            *self._extra_args,
        ]
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        lines: queue.Queue[str | None] = queue.Queue()

        def read_stdout() -> None:
            try:
                assert process.stdout is not None
                for raw_line in iter(process.stdout.readline, b""):
                    text = raw_line.decode("utf-8", errors="replace").strip()
                    if text:
                        lines.put(text)
            finally:
                lines.put(None)  # sentinel: stdout closed

        reader = threading.Thread(target=read_stdout, daemon=True, name="whisper-stdout")
        reader.start()

        accumulated = ""
        try:
            for chunk in audio_chunks:
                if token is not None:
                    token.throw_if_cancelled()
                if process.stdin is not None:
                    process.stdin.write(chunk)
                    process.stdin.flush()
            if process.stdin is not None:
                process.stdin.close()

            while True:
                text = lines.get()
                if text is None:
                    break
                accumulated = f"{accumulated} {text}".strip()
                yield STTChunk(text=accumulated, is_final=False, language=language)

            if accumulated:
                yield STTChunk(text=accumulated, is_final=True, language=language)
        finally:
            reader.join(timeout=5.0)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()

    def detect_language(
        self,
        audio: bytes,
        *,
        token: CancellationToken | None = None,
    ) -> str:
        """Detect the language of the audio using whisper.cpp.

        Runs whisper.cpp with `--detect-language` and parses the detected
        language code from the output.

        Args:
            audio: 16 kHz mono PCM16 WAV bytes.
            token: Optional cancellation token.

        Returns:
            ISO 639-1 language code (e.g., 'en', 'pt', 'es').

        Raises:
            ProviderRuntimeError: if whisper.cpp fails or language cannot be detected.
        """
        if token is not None:
            token.throw_if_cancelled()

        require_whisper_format(audio)
        # Build argv with --detect-language flag
        argv = list(self._argv)
        # Remove -np (no progress) to allow output
        argv = [arg for arg in argv if arg != "-np"]
        argv.extend(["--detect-language"])
        # Temporarily override argv for this run
        original_argv = self._argv
        self._argv = argv
        try:
            raw = self.run(audio).decode("utf-8", errors="replace")
        finally:
            self._argv = original_argv
        # Parse detected language from output like "detected language: en"
        match = re.search(r"detected language:\s*(\w+)", raw, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        # Fallback: check for "language: en" format
        match = re.search(r"language:\s*(\w+)", raw, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        raise ProviderRuntimeError(
            "whispercpp",
            "stt",
            "could not detect language from whisper.cpp output",
            command=" ".join(argv),
            stderr=raw[:500],
        )

    @staticmethod
    def parse_word_timestamps(raw: str) -> list[WordTiming]:
        """Extract ``(word, start_ms, end_ms)`` triples from whisper.cpp output.

        Returns an empty list for builds that do not emit word timestamps —
        callers must treat timing as optional metadata, never as a requirement.
        """
        timings: list[WordTiming] = []
        for match in _WORD_TIMESTAMP.finditer(raw):
            sh, sm, ss, sms, eh, em, es, ems, word = match.groups()
            timings.append(
                WordTiming(
                    word=word,
                    start_ms=_hms_to_ms(sh, sm, ss, sms),
                    end_ms=_hms_to_ms(eh, em, es, ems),
                )
            )
        return timings

    @staticmethod
    def parse_transcript(raw: str) -> str:
        """Reduce whisper.cpp output to just the spoken text.

        Tolerant by design: output format varies between forks, and a leading or
        trailing artefact should not cost the caller a transcript.
        """
        text = _TIMESTAMP.sub("", raw)
        text = _BRACKETED.sub("", text)
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not _FILE_WRITTEN.match(line)
        ]
        return " ".join(lines).strip()

    # -- Provider protocol -----------------------------------------------------

    @property
    def name(self) -> str:
        return "whispercpp"

    @property
    def modality(self) -> str:
        return "stt"

    @property
    def _sample_rate(self) -> int:
        return 16000

    def capabilities(self) -> ProviderCapabilities:
        from voicevision.core.protocols import ProviderCapabilities
        return ProviderCapabilities(
            streaming=True,
            languages=frozenset({"auto", "en", "pt", "es", "fr", "de", "it", "zh", "ja", "ko"}),
            models=frozenset({"tiny", "base", "small", "medium", "large"}),
            max_concurrent=1,
            supports_cancellation=True,
        )

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        self.close()

    def health_check(self) -> bool:
        return self.available()


#: Default sample rate for whisper.cpp
DEFAULT_SAMPLE_RATE: Final = 16000

#: Default chunk size for streaming (ms)
DEFAULT_CHUNK_SIZE_MS: Final = 1500

#: Default overlap between chunks (ms)
DEFAULT_OVERLAP_MS: Final = 500

