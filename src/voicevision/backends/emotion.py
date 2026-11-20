"""Emotion detection on transcript text.

Simple rule-based implementation with no external dependencies.

Implements EmotionProvider protocol (M1).
"""

from __future__ import annotations

from typing import ClassVar

from voicevision.core.cancellation import CancellationToken
from voicevision.core.protocols import EmotionResult, ProviderCapabilities, ProviderLifecycle


class SimpleEmotionBackend:
    """Simple rule-based emotion detection.

    Implements EmotionProvider protocol.

    Uses keyword matching to classify text as positive, negative, or neutral.
    No external model dependencies.
    """

    # Positive emotion keywords
    POSITIVE_KEYWORDS: ClassVar[set[str]] = {
        "happy",
        "joy",
        "love",
        "excited",
        "great",
        "wonderful",
        "amazing",
        "fantastic",
        "awesome",
        "good",
        "nice",
        "pleased",
        "glad",
        "delighted",
        "thrilled",
        "cheerful",
        "content",
        "satisfied",
        "grateful",
        "thankful",
        "blessed",
        "lucky",
        "fortunate",
        "success",
        "win",
        "victory",
        "celebrate",
        "party",
        "fun",
        "enjoy",
        "like",
        "beautiful",
        "lovely",
        "perfect",
        "excellent",
        "superb",
        "brilliant",
        "outstanding",
        "marvelous",
        "splendid",
        "magnificent",
        "terrific",
        "fabulous",
    }

    # Negative emotion keywords
    NEGATIVE_KEYWORDS: ClassVar[set[str]] = {
        "sad",
        "angry",
        "upset",
        "frustrated",
        "disappointed",
        "worried",
        "anxious",
        "stressed",
        "tired",
        "exhausted",
        "bad",
        "terrible",
        "awful",
        "horrible",
        "dreadful",
        "unhappy",
        "miserable",
        "depressed",
        "lonely",
        "alone",
        "hurt",
        "pain",
        "sorry",
        "regret",
        "guilt",
        "shame",
        "fear",
        "scared",
        "afraid",
        "panic",
        "nervous",
        "tense",
        "mad",
        "furious",
        "rage",
        "hate",
        "dislike",
        "annoyed",
        "irritated",
        "bored",
        "sick",
        "ill",
        "problem",
        "issue",
        "trouble",
        "difficult",
        "hard",
        "fail",
        "failure",
        "lost",
        "lose",
        "mistake",
        "error",
        "wrong",
        "broken",
    }

    def __init__(self) -> None:
        pass

    @classmethod
    def available(cls) -> bool:
        """Always available - no external dependencies."""
        return True

    @classmethod
    def install_hint(cls) -> str:
        return "Built-in: no installation required"

    # -- EmotionProvider protocol ----------------------------------------------

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
            EmotionResult with label (positive/negative/neutral) and confidence score.
        """
        if token is not None:
            token.throw_if_cancelled()

        if not text or not text.strip():
            return EmotionResult(label="neutral", score=0.5)

        words = text.lower().split()
        if not words:
            return EmotionResult(label="neutral", score=0.5)

        positive_count = sum(1 for w in words if w in self.POSITIVE_KEYWORDS)
        negative_count = sum(1 for w in words if w in self.NEGATIVE_KEYWORDS)

        total_emotion_words = positive_count + negative_count

        if total_emotion_words == 0:
            return EmotionResult(label="neutral", score=0.5)

        # Calculate confidence based on ratio of emotion words
        positive_ratio = positive_count / total_emotion_words
        confidence = min(0.5 + (abs(positive_ratio - 0.5) * 0.5), 0.95)

        if positive_count > negative_count:
            return EmotionResult(label="positive", score=confidence)
        if negative_count > positive_count:
            return EmotionResult(label="negative", score=confidence)
        return EmotionResult(label="neutral", score=0.5)

    def detect_audio(
        self,
        audio: bytes,
        *,
        sample_rate: int = 16000,
        token: CancellationToken | None = None,
    ) -> EmotionResult:
        """Keyword backend is text-only; use the ML backend for audio."""
        if token is not None:
            token.throw_if_cancelled()
        raise NotImplementedError(
            "SimpleEmotionBackend is text-only; use MLEmotionBackend for audio"
        )

    # -- Provider protocol -----------------------------------------------------

    @property
    def name(self) -> str:
        return "simple"

    @property
    def modality(self) -> str:
        return "emotion"

    def capabilities(self) -> ProviderCapabilities:
        from voicevision.core.protocols import ProviderCapabilities
        return ProviderCapabilities(
            streaming=False,
            languages=frozenset({"en", "pt"}),  # English and Portuguese keywords
            models=frozenset(),
            max_concurrent=100,
            supports_cancellation=True,
        )

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        return True


# Default backend instance
_default_backend: SimpleEmotionBackend | None = None


def get_emotion_backend() -> SimpleEmotionBackend:
    """Get or create the default emotion backend."""
    global _default_backend
    if _default_backend is None:
        _default_backend = SimpleEmotionBackend()
    return _default_backend


def detect_emotion(text: str) -> EmotionResult:
    """Convenience function to detect emotion using the default backend."""
    return get_emotion_backend().detect(text)
