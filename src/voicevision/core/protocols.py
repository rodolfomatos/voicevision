"""Core protocol definitions for voicevision backends.

All backends implement these protocols via structural subtyping (typing.Protocol).
No inheritance required — any class with matching methods qualifies.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMBackend(Protocol):
    """Language model backend for text generation."""

    __slots__ = ()

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text completion for the given prompt.

        Args:
            prompt: Input text prompt.
            **kwargs: Backend-specific parameters (temperature, max_tokens, etc.).

        Returns:
            Generated text completion.
        """
        ...

    def generate_stream(self, prompt: str, **kwargs: Any) -> Iterator[str]:
        """Stream text generation (optional).

        Args:
            prompt: Input text prompt.
            **kwargs: Backend-specific parameters.

        Yields:
            Text chunks as they are generated.
        """
        ...


@runtime_checkable
class STTBackend(Protocol):
    """Speech-to-text backend for audio transcription."""

    __slots__ = ()

    def transcribe(self, audio_data: bytes, **kwargs: Any) -> str:
        """Transcribe audio to text.

        Args:
            audio_data: Raw audio bytes (WAV, MP3, etc. — backend-dependent).
            **kwargs: Backend-specific parameters (language, etc.).

        Returns:
            Transcribed text.
        """
        ...

    def transcribe_stream(self, audio_chunk: bytes, **kwargs: Any) -> Iterator[str]:
        """Stream transcription (optional).

        Args:
            audio_chunk: Audio chunk bytes.
            **kwargs: Backend-specific parameters.

        Yields:
            Partial transcriptions.
        """
        ...


@runtime_checkable
class TTSBackend(Protocol):
    """Text-to-speech backend for speech synthesis."""

    __slots__ = ()

    def synthesize(self, text: str, **kwargs: Any) -> bytes:
        """Synthesize speech from text.

        Args:
            text: Input text to synthesize.
            **kwargs: Backend-specific parameters (voice, speed, etc.).

        Returns:
            Audio bytes (WAV format recommended).
        """
        ...

    def synthesize_stream(self, text: str, **kwargs: Any) -> Iterator[bytes]:
        """Stream synthesis (optional).

        Args:
            text: Input text.
            **kwargs: Backend-specific parameters.

        Yields:
            Audio chunks as they are generated.
        """
        ...


@runtime_checkable
class VisionBackend(Protocol):
    """Vision backend for image description/analysis."""

    __slots__ = ()

    def describe(self, image_data: bytes, prompt: str | None = None, **kwargs: Any) -> str:
        """Describe or analyze an image.

        Args:
            image_data: Raw image bytes (JPEG, PNG, etc. — backend-dependent).
            prompt: Optional prompt to guide description.
            **kwargs: Backend-specific parameters.

        Returns:
            Text description/analysis.
        """
        ...


@runtime_checkable
class CameraBackend(Protocol):
    """Camera backend for image capture."""

    __slots__ = ()

    def capture(self, **kwargs: Any) -> bytes:
        """Capture a single frame.

        Args:
            **kwargs: Backend-specific parameters (resolution, format, etc.).

        Returns:
            Image bytes (JPEG/PNG).
        """
        ...

    def capture_stream(self, **kwargs: Any) -> Iterator[bytes]:
        """Stream frames (optional).

        Args:
            **kwargs: Backend-specific parameters.

        Yields:
            Image frames as bytes.
        """
        ...

    def close(self) -> None:
        """Release camera resources."""
        ...
