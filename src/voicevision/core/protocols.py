"""Core protocol definitions for voicevision providers.

All providers implement these protocols via structural subtyping (typing.Protocol).
No inheritance required — any class with matching methods qualifies.

Version: 2.0.0 (M1 Core Abstraction)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator, Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# Import the real CancellationToken to avoid type mismatch with implementations
from voicevision.core.cancellation import CancellationToken

# =============================================================================
# Capability & Lifecycle Metadata
# =============================================================================

@dataclass(frozen=True)
class ProviderCapabilities:
    """Capabilities declared by a provider.

    Used by the registry and model router for selection.
    """
    streaming: bool = False
    languages: frozenset[str] = frozenset()
    models: frozenset[str] = frozenset()
    max_concurrent: int = 1
    supports_cancellation: bool = False


@runtime_checkable
class ProviderLifecycle(Protocol):
    """Provider lifecycle management."""

    __slots__ = ()

    def initialize(self) -> None:
        """Initialize the provider (load model, start daemon, etc.)."""
        ...

    def shutdown(self) -> None:
        """Shutdown the provider (stop daemon, release resources)."""
        ...

    def health_check(self) -> bool:
        """Quick health check. Returns True if healthy."""
        ...


@runtime_checkable
class Provider(Protocol):
    """Base protocol for all providers."""

    __slots__ = ()

    @property
    def name(self) -> str:
        """Unique provider name within modality."""
        ...

    @property
    def modality(self) -> str:
        """Modality: stt, llm, tts, vad, vision, wakeword, speakerid, emotion."""
        ...

    def capabilities(self) -> ProviderCapabilities:
        """Declare provider capabilities."""
        ...

    def lifecycle(self) -> ProviderLifecycle:
        """Return lifecycle manager."""
        ...

    @classmethod
    def available(cls) -> bool:
        """Fast check if provider can run (executable exists, deps installed)."""
        ...

    @classmethod
    def install_hint(cls) -> str:
        """User-actionable installation instruction."""
        ...


# =============================================================================
# Chunk Types for Streaming
# =============================================================================

@dataclass(frozen=True)
class STTChunk:
    """Streaming STT chunk."""
    text: str
    is_final: bool = False
    language: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class LLMChunk:
    """Streaming LLM chunk."""
    content: str
    is_final: bool = False
    thinking: str = ""


@dataclass(frozen=True)
class TTSChunk:
    """Streaming TTS chunk."""
    audio: bytes
    is_final: bool = False
    sample_rate: int = 16000


@dataclass(frozen=True)
class SpeakerMatch:
    """Result of identifying a single utterance."""

    label: str
    score: float = 0.0


@dataclass(frozen=True)
class SpeakerSegment:
    """A labelled span of audio, used by diarization and streaming speaker ID."""

    label: str
    start_ms: int
    end_ms: int
    score: float = 0.0


# =============================================================================
# Provider Protocols
# =============================================================================

@runtime_checkable
class STTProvider(Provider, Protocol):
    """Speech-to-text provider."""

    __slots__ = ()

    @property
    def modality(self) -> str:
        return "stt"

    def transcribe(
        self,
        audio: bytes,
        *,
        language: str | None = None,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> str:
        """Transcribe complete audio to text.

        Args:
            audio: PCM16 mono audio at 16kHz (or provider-specific format).
            language: Language code (e.g., 'en', 'pt') or 'auto' for detection.
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Returns:
            Transcribed text. Empty string if no speech detected.

        Raises:
            ProviderUnavailableError: If provider not installed/configured.
            ProviderTimeoutError: If deadline exceeded.
            ProviderRuntimeError: If transcription fails.
        """
        ...

    def transcribe_stream(
        self,
        audio_chunks: Generator[bytes, None, None] | AsyncGenerator[bytes, None],
        *,
        language: str | None = None,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> Generator[STTChunk, None, None] | AsyncGenerator[STTChunk, None]:
        """Stream transcription from audio chunks.

        Args:
            audio_chunks: Generator yielding audio chunks.
            language: Language code or 'auto'.
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Yields:
            STTChunk with partial/final transcripts.
        """
        ...

    def detect_language(
        self,
        audio: bytes,
        *,
        token: CancellationToken | None = None,
    ) -> str:
        """Detect language from audio.

        Args:
            audio: PCM16 mono audio.
            token: Optional cancellation token.

        Returns:
            ISO 639-1 language code (e.g., 'en', 'pt').

        Raises:
            ProviderRuntimeError: If detection fails.
        """
        ...


@runtime_checkable
class LLMProvider(Provider, Protocol):
    """Language model provider."""

    __slots__ = ()

    @property
    def modality(self) -> str:
        return "llm"

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        stop: list[str] | None = None,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate completion (non-streaming).

        Args:
            prompt: Input prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            stop: Stop sequences.
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Returns:
            Generated text (reasoning traces already filtered if applicable).
        """
        ...

    def generate_stream(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        stop: list[str] | None = None,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> Generator[LLMChunk, None, None] | AsyncGenerator[LLMChunk, None]:
        """Stream completion chunks.

        Args:
            prompt: Input prompt.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            stop: Stop sequences.
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Yields:
            LLMChunk with content chunks.
        """
        ...

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        stop: list[str] | None = None,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> Completion:
        """Generate completion with separate reasoning trace.

        Returns:
            Completion object with content and thinking separated.
        """
        ...


@dataclass(frozen=True)
class Completion:
    """LLM completion with separated reasoning."""
    content: str
    thinking: str = ""
    raw: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.raw is None:
            object.__setattr__(self, "raw", {})

    @property
    def has_thinking(self) -> bool:
        return bool(self.thinking.strip())


@runtime_checkable
class TTSProvider(Provider, Protocol):
    """Text-to-speech provider."""

    __slots__ = ()

    @property
    def modality(self) -> str:
        return "tts"

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> bytes:
        """Synthesize speech from text (non-streaming).

        Args:
            text: Text to synthesize.
            voice: Voice identifier.
            speed: Speech speed multiplier.
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Returns:
            Audio bytes (WAV format, 16kHz mono PCM16 recommended).
        """
        ...

    def synthesize_stream(
        self,
        text_chunks: Generator[str, None, None] | AsyncGenerator[str, None],
        *,
        voice: str | None = None,
        speed: float = 1.0,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> Generator[TTSChunk, None, None] | AsyncGenerator[TTSChunk, None]:
        """Stream synthesis from text chunks.

        Args:
            text_chunks: Generator yielding text chunks.
            voice: Voice identifier.
            speed: Speech speed multiplier.
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Yields:
            TTSChunk with audio chunks.
        """
        ...


@runtime_checkable
class VADProvider(Provider, Protocol):
    """Voice activity detection provider."""

    __slots__ = ()

    @property
    def modality(self) -> str:
        return "vad"

    def process_frame(
        self,
        frame: bytes,
        *,
        token: CancellationToken | None = None,
    ) -> bool:
        """Process a single audio frame.

        Args:
            frame: Audio frame (30ms at sample_rate, 16-bit mono).
            token: Optional cancellation token.

        Returns:
            True if speech detected in frame.
        """
        ...

    def segment(
        self,
        audio: bytes,
        *,
        token: CancellationToken | None = None,
    ) -> Generator[tuple[int, int], None, None]:
        """Segment audio into utterance byte ranges.

        Args:
            audio: Complete PCM16 audio.
            token: Optional cancellation token.

        Yields:
            (start_byte, end_byte) pairs for each utterance.
        """
        ...

    @property
    def frame_bytes(self) -> int:
        """Frame size in bytes for the configured sample rate."""
        ...

    @property
    def frame_ms(self) -> int:
        """Frame duration in milliseconds."""
        ...

    @property
    def sample_rate(self) -> int:
        """Sample rate in Hz."""
        ...

    @property
    def max_utterance_ms(self) -> int:
        """Maximum utterance duration in milliseconds."""
        ...


@runtime_checkable
class VisionProvider(Provider, Protocol):
    """Vision/image analysis provider."""

    __slots__ = ()

    @property
    def modality(self) -> str:
        return "vision"

    def describe(
        self,
        image: bytes,
        *,
        prompt: str | None = None,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> str:
        """Describe or analyze an image.

        Args:
            image: Raw image bytes (JPEG/PNG).
            prompt: Optional prompt to guide description.
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Returns:
            Text description/analysis.
        """
        ...

    def analyze(
        self,
        image: bytes,
        *,
        task: str = "describe",
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Analyze image with structured output.

        Args:
            image: Raw image bytes.
            task: Analysis task ('describe', 'ocr', 'detect', 'classify').
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Returns:
            Structured result dict.
        """
        ...


@runtime_checkable
class WakeWordProvider(Provider, Protocol):
    """Wake word detection provider."""

    __slots__ = ()

    @property
    def modality(self) -> str:
        return "wakeword"

    def process_frame(
        self,
        frame: bytes,
        *,
        token: CancellationToken | None = None,
    ) -> str | None:
        """Process frame for wake word.

        Args:
            frame: Audio frame.
            token: Optional cancellation token.

        Returns:
            Matched wake word if detected, None otherwise.
        """
        ...

    def check(
        self,
        audio: bytes,
        *,
        token: CancellationToken | None = None,
    ) -> str | None:
        """Check complete audio for wake word.

        Args:
            audio: Complete audio buffer.
            token: Optional cancellation token.

        Returns:
            Matched wake word if detected, None otherwise.
        """
        ...

    @property
    def wake_words(self) -> frozenset[str]:
        """Configured wake words."""
        ...


@runtime_checkable
class SpeakerStoreProtocol(Protocol):
    """Persistence contract for enrolled speaker embeddings (T092)."""

    __slots__ = ()

    @property
    def path(self) -> str | None: ...

    def add(self, label: str, vector: Iterable[float]) -> None: ...

    def remove(self, label: str) -> bool: ...

    def vectors(self, label: str) -> tuple[tuple[float, ...], ...]: ...

    def mean(self, label: str) -> tuple[float, ...] | None: ...

    def labels(self) -> tuple[str, ...]: ...

    def clear(self) -> None: ...

    def flush(self) -> None: ...


@runtime_checkable
class SpeakerIDProvider(Provider, Protocol):
    """Speaker identification provider."""

    __slots__ = ()

    @property
    def modality(self) -> str:
        return "speakerid"

    def identify(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> str:
        """Identify speaker from audio.

        Args:
            audio: PCM16 mono audio.
            sample_rate: Sample rate in Hz.
            token: Optional cancellation token.

        Returns:
            Speaker label (e.g., "Speaker 1").
        """
        ...

    def enroll(
        self,
        audio: bytes,
        *,
        label: str,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> None:
        """Enroll a new speaker.

        Args:
            audio: Reference audio for speaker.
            label: Speaker label.
            sample_rate: Sample rate in Hz.
            token: Optional cancellation token.
        """
        ...

    def reset(self) -> None:
        """Reset speaker profiles for new session."""
        ...

    def remove(self, label: str) -> bool:
        """Remove an enrolled speaker. Returns True if it existed (T092)."""
        ...

    def identify_stream(
        self,
        audio_chunks: Iterable[bytes],
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> Generator[SpeakerSegment, None, None]:
        """Yield speaker labels for successive audio windows (T092)."""
        ...

    def diarize(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> list[SpeakerSegment]:
        """Split multi-speaker audio into labelled turns (T092)."""
        ...


@runtime_checkable
class EmotionProvider(Provider, Protocol):
    """Emotion detection provider."""

    __slots__ = ()

    @property
    def modality(self) -> str:
        return "emotion"

    def detect(
        self,
        text: str,
        *,
        token: CancellationToken | None = None,
    ) -> EmotionResult:
        """Detect emotion from text.

        Args:
            text: Input text to analyze.
            token: Optional cancellation token.

        Returns:
            EmotionResult with label and score.
        """
        ...

    def detect_audio(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> EmotionResult:
        """Detect emotion from PCM16 audio (T093)."""
        ...


@dataclass(frozen=True)
class EmotionResult:
    """Result of emotion detection."""
    label: str  # positive, negative, neutral, etc.
    score: float  # 0.0 - 1.0
    # Confidence for every considered emotion (multi-label support, T093).
    scores: dict[str, float] = field(default_factory=dict)


# =============================================================================
# Type Aliases
# =============================================================================

ModalityName = str  # stt | llm | tts | vad | vision | wakeword | speakerid | emotion

ProviderType = (
    STTProvider | LLMProvider | TTSProvider | VADProvider |
    VisionProvider | WakeWordProvider | SpeakerIDProvider | EmotionProvider
)
