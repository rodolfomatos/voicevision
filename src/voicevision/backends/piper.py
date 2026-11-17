"""Text to speech via the piper CLI (ADR-001).

piper is a one-shot program: it reads text from stdin, writes a WAV file to
stdout, and exits. That matches SubprocessBackend's one-shot semantics exactly
— see that module's docstring for why it spawns per call rather than keeping a
child warm.

Implements TTSProvider protocol (M1).
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from typing import ClassVar

from voicevision.backends.subprocess_backend import SubprocessBackend
from voicevision.core.protocols import ProviderCapabilities, ProviderLifecycle, TTSChunk


class PiperBackend(SubprocessBackend):
    """Synthesise speech via the piper CLI.

    Implements TTSProvider protocol.
    The voice model (ONNX) is supplied by the caller; this class never downloads
    anything.
    """

    executable: ClassVar[str] = "piper"

    install_hint: ClassVar[str] = (
        "Install piper: pip install piper-tts, or build from https://github.com/rhasspy/piper"
    )

    def __init__(
        self,
        model: str,
        *,
        voice: str = "",
        length_scale: float = 1.0,
        timeout: float | None = None,
        binary: str | None = None,
    ) -> None:
        if not model:
            raise ValueError("model path is required — this backend does not download models")
        self._model = model
        self._voice = voice
        self._length_scale = length_scale

        argv = [
            binary or self.executable,
            "--model",
            model,
            "--output_file",
            "-",  # write WAV to stdout
        ]
        if voice:
            argv += ["--voice", voice]
        if length_scale != 1.0:
            argv += ["--length_scale", str(length_scale)]

        super().__init__(
            argv,
            timeout=timeout,
            name="piper",
        )

    @classmethod
    def available(cls) -> bool:
        return shutil.which(cls.executable) is not None

    # install_hint is a class attribute (line 32). The protocol expects a classmethod,
    # but @runtime_checkable only validates instance methods. Class attribute works.

    # -- TTSProvider protocol --------------------------------------------------

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
        token: CancellationToken | None = None,
        **kwargs: object,
    ) -> bytes:
        """Synthesise speech from text (non-streaming).

        Args:
            text: Text to synthesise. Empty string returns empty bytes without
                spawning piper.
            voice: Voice identifier (overrides constructor).
            speed: Speech speed multiplier (via length_scale).
            token: Optional cancellation token.
            **kwargs: Ignored; per-call overrides belong on the constructor so
                they land in argv rather than being silently dropped.

        Returns:
            WAV bytes. Empty bytes for empty input.

        Raises:
            ProviderUnavailableError: if piper is not installed.
            ProviderRuntimeError: if piper fails.
        """
        if token is not None:
            token.throw_if_cancelled()

        del kwargs
        if not text:
            return b""

        # Build argv for this call (don't modify instance state)
        argv = [
            self._argv[0],  # binary
            "--model",
            self._model,
            "--output_file",
            "-",
        ]
        effective_voice = voice if voice is not None else self._voice
        if effective_voice:
            argv += ["--voice", effective_voice]
        effective_speed = speed if speed != 1.0 else self._length_scale
        if effective_speed != 1.0:
            argv += ["--length_scale", str(effective_speed)]

        # Temporarily replace argv for this run
        original_argv = self._argv
        self._argv = argv
        try:
            return self.run(text.encode("utf-8"))
        finally:
            self._argv = original_argv

    def synthesize_stream(
        self,
        text_chunks: Generator[str, None, None],
        *,
        voice: str | None = None,
        speed: float = 1.0,
        token: CancellationToken | None = None,
        **kwargs: object,
    ) -> Generator[TTSChunk, None, None]:
        """Stream synthesis from text chunks.

        piper is a one-shot CLI. This method buffers all chunks and
        synthesizes once for compatibility.
        """
        if token is not None:
            token.throw_if_cancelled()

        # Buffer all text chunks
        text_buffer = []
        for chunk in text_chunks:
            if token is not None:
                token.throw_if_cancelled()
            if chunk:
                text_buffer.append(chunk)

        if not text_buffer:
            return
            yield  # Make this a generator

        full_text = "".join(text_buffer)
        audio = self.synthesize(full_text, voice=voice, speed=speed, token=token)
        yield TTSChunk(audio=audio, is_final=True, sample_rate=16000)

    def _rebuild_argv(self) -> None:
        """Rebuild argv with current voice/speed settings."""
        argv = [
            self._argv[0],  # binary
            "--model",
            self._model,
            "--output_file",
            "-",
        ]
        if self._voice:
            argv += ["--voice", self._voice]
        if self._length_scale != 1.0:
            argv += ["--length_scale", str(self._length_scale)]
        self._argv = argv

    def _parse_error(self, stderr: str) -> str:
        """Extract a human-readable error message from piper's stderr."""
        lines = stderr.strip().splitlines()
        for line in reversed(lines):
            if "error" in line.lower():
                return line.strip()
        return stderr.strip() or "piper exited with non-zero status"

    # -- Provider protocol -----------------------------------------------------

    @property
    def name(self) -> str:
        return "piper"

    @property
    def modality(self) -> str:
        return "tts"

    def capabilities(self) -> ProviderCapabilities:
        from voicevision.core.protocols import ProviderCapabilities
        return ProviderCapabilities(
            streaming=False,
            languages=frozenset({"en", "pt", "es", "fr", "de", "it"}),
            models=frozenset({"en_US-lessac-medium", "en_US-amy-low", "pt_BR-faber-medium"}),
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


# Forward reference for type hints
class CancellationToken:
    """Forward reference."""
    def throw_if_cancelled(self) -> None: ...
