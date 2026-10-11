"""Text to speech via the piper CLI (ADR-001).

piper is a one-shot program: it reads text from stdin, writes a WAV file to
stdout, and exits. That matches SubprocessBackend's one-shot semantics exactly
— see that module's docstring for why it spawns per call rather than keeping a
child warm.
"""

from __future__ import annotations

import shutil
from typing import ClassVar

from voicevision.backends.subprocess_backend import SubprocessBackend
from voicevision.errors import BackendExecutionError, BackendNotAvailableError


class PiperBackend(SubprocessBackend):
    """Synthesise speech via the piper CLI.

    The voice model (ONNX) is supplied by the caller; this class never downloads
    anything.
    """

    executable: ClassVar[str] = "piper"

    install_hint: ClassVar[str] = (
        "Install piper: pip install piper-tts, or build from "
        "https://github.com/rhasspy/piper"
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
            "--model", model,
            "--output_file", "-",  # write WAV to stdout
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

    def synthesize(self, text: str, **kwargs: object) -> bytes:
        """Synthesise speech from text.

        Args:
            text: Text to synthesise. Empty string returns empty bytes without
                spawning piper.
            **kwargs: Ignored; per-call overrides belong on the constructor so
                they land in argv rather than being silently dropped.

        Returns:
            WAV bytes. Empty bytes for empty input.

        Raises:
            BackendNotAvailableError: if piper is not installed.
            BackendExecutionError: if piper fails.
        """
        del kwargs
        if not text:
            return b""
        # piper reads UTF-8 text from stdin, writes binary WAV to stdout.
        return self.run(text.encode("utf-8"))

    def _parse_error(self, stderr: str) -> str:
        """Extract a human-readable error message from piper's stderr."""
        lines = stderr.strip().splitlines()
        for line in reversed(lines):
            if "error" in line.lower():
                return line.strip()
        return stderr.strip() or "piper exited with non-zero status"