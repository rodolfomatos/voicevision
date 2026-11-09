"""Emotion detection on transcript text.

Simple rule-based implementation with no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass
class EmotionResult:
    """Result of emotion detection."""

    label: str
    score: float


class SimpleEmotionBackend:
    """Simple rule-based emotion detection.

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

    def detect(self, text: str) -> EmotionResult:
        """Detect emotion from text.

        Args:
            text: Input text to analyze.

        Returns:
            EmotionResult with label (positive/negative/neutral) and confidence score.
        """
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
