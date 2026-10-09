"""Speech to text via the whisper.cpp CLI (ADR-001).

whisper.cpp is a one-shot program: it reads a WAV file from stdin, prints a
transcript, and exits. That matches SubprocessBackend's semantics exactly — see
that module's docstring for why it spawns per call rather than keeping a child
warm.
"""

from __future__ import annotations

import re
import shutil
from typing import ClassVar, Final

from voicevision.audio import require_whisper_format
from voicevision.backends.subprocess_backend import SubprocessBackend

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

    def transcribe(self, audio: bytes, **kwargs: object) -> str:
        """Transcribe a WAV file.

        Args:
            audio: 16 kHz mono PCM16 WAV bytes.
            **kwargs: ignored; per-call overrides belong on the constructor so
                they land in argv rather than being silently dropped.

        Returns:
            The transcript. Empty string when the audio contains no speech —
                that is a result, not an error.

        Raises:
            AudioFormatError: if the audio is not 16 kHz mono PCM16.
            BackendNotAvailableError: if whisper.cpp is not installed.
            BackendExecutionError: if whisper.cpp fails.
        """
        del kwargs
        # Validate before spawning. A format problem is the caller's bug and
        # naming it precisely is more useful than whatever whisper.cpp makes of
        # it. Never resample here — see voicevision.audio.
        require_whisper_format(audio)

        raw = self.run(audio).decode("utf-8", errors="replace")
        return self.parse_transcript(raw)

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


DEFAULT_MODEL_NAME: Final = "whisper-base.bin"
