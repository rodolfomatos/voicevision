"""Speech to text via the whisper.cpp CLI (ADR-001).

whisper.cpp is a one-shot program: it reads a WAV file from stdin, prints a
transcript, and exits. That matches SubprocessBackend's semantics exactly — see
that module's docstring for why it spawns per call rather than keeping a child
warm.

Implements STTProvider protocol (M1) with streaming support via chunked processing.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Generator
from typing import ClassVar, Final

from voicevision.audio import require_whisper_format
from voicevision.backends.subprocess_backend import SubprocessBackend
from voicevision.core.protocols import (
    ProviderCapabilities,
    ProviderLifecycle,
    STTChunk,
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
    ) -> tuple[str, list[STTChunk]]:
        """Process transcript chunk and return complete sentences as partial results."""
        combined = accumulated_text + transcript
        sentences = extract_sentences(combined)

        chunks: list[STTChunk] = []
        new_accumulated = accumulated_text

        # Emit complete sentences as partial results
        for sentence in sentences[:-1]:  # All but last (might be incomplete)
            if sentence != accumulated_text:
                chunks.append(
                    STTChunk(
                        text=sentence,
                        is_final=False,
                        language=language,
                        start_ms=None,
                        end_ms=None,
                    )
                )
                accumulated_text = sentence

        # Keep incomplete last sentence for next iteration
        new_accumulated = sentences[-1] if sentences else ""

        return new_accumulated, chunks

    def transcribe_stream(
        self,
        audio_chunks: Generator[bytes, None, None],
        *,
        language: str | None = None,
        token: CancellationToken | None = None,
        **kwargs: object,
    ) -> Generator[STTChunk, None, None]:
        """Stream transcription via chunked processing with partial results.

        whisper.cpp is a one-shot CLI, so we implement streaming by:
        1. Buffering incoming audio chunks
        2. When enough audio accumulates (chunk_size_ms), transcribe it
        3. Use sentence boundary detection to emit partial results
        4. Yield partial results with is_final=False, final with is_final=True

        Args:
            audio_chunks: Generator yielding audio chunks (PCM16 WAV bytes).
            language: Language code (e.g., 'en', 'pt') or 'auto' for detection.
                If None, uses the language from constructor.
            token: Optional cancellation token.
            **kwargs: Additional options:
                - chunk_size_ms: Audio chunk size in ms (default: 1500)
                - overlap_ms: Overlap between chunks in ms (default: 500)

        Yields:
            STTChunk with partial/final transcripts.
        """
        chunk_size_ms, overlap_ms, chunk_bytes, overlap_bytes = self._extract_chunk_params({})

        # Language detection state
        detected_language: str | None = None
        if language == "auto":
            language = None  # Will be detected on first chunk

        # Buffer for accumulating audio
        audio_buffer = bytearray()
        accumulated_text = ""

        for chunk in audio_chunks:
            if token is not None:
                token.throw_if_cancelled()
            audio_buffer.extend(chunk)

            # Process when we have enough audio
            while len(audio_buffer) >= chunk_bytes:
                # Extract chunk with overlap
                process_chunk = bytes(audio_buffer[:chunk_bytes])
                # Keep overlap for next iteration
                audio_buffer = audio_buffer[chunk_bytes - overlap_bytes:]

                # Transcribe this chunk
                transcript, detected_lang = self._transcribe_chunk(
                    process_chunk, language, token
                )
                if detected_language is None and detected_lang:
                    language = detected_lang

                # Process transcript chunk
                accumulated_text, chunks = self._process_transcript_chunk(
                    transcript, accumulated_text, language, language
                )
                yield from chunks

        # Process remaining audio
        if audio_buffer:
            transcript, detected_lang = self._transcribe_chunk(
                bytes(audio_buffer), language, token
            )
            combined = accumulated_text + transcript
            sentences = extract_sentences(combined)
            for sentence in sentences[:-1]:
                if sentence != accumulated_text:
                    yield STTChunk(
                        text=sentence,
                        is_final=False,
                        language=language or detected_language,
                    )
                    accumulated_text = sentence
            accumulated_text = sentences[-1] if sentences else ""

        # Emit final result
        final_text = accumulated_text or combined
        if final_text.strip():
            yield STTChunk(
                text=final_text,
                is_final=True,
                language=language,
            )

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


#: whisper.cpp prefixes each segment with `[00:00:00.000 --> 00:00:02.000]`.
#: `-nt` suppresses these, but forks differ, so strip defensively rather than
#: trust the flag was honoured.
_TIMESTAMP = re.compile(r"^\s*\[[^\]]*-->[^\]]*\]\s*", re.MULTILINE)

#: Some builds bracket non-speech markers such as `[BLANK_AUDIO]` or `(music)`.
_BRACKETED = re.compile(r"\[[A-Z_]{3,}\]")

#: Backends that write a transcript file instead of stdout put this on stdout.
_FILE_WRITTEN = re.compile(r"^\s*.*\.txt\s*$", re.MULTILINE)

#: Default sample rate for whisper.cpp
DEFAULT_SAMPLE_RATE: Final = 16000

#: Default chunk size for streaming (ms)
DEFAULT_CHUNK_SIZE_MS: Final = 1500

#: Default overlap between chunks (ms)
DEFAULT_OVERLAP_MS: Final = 500


# Forward reference for type hints
class CancellationToken:
    """Forward reference."""
    def throw_if_cancelled(self) -> None: ...

