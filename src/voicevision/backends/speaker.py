"""Speaker identification (diarization-lite) on audio segments.

Simple session-based speaker tracking using audio features.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class SpeakerProfile:
    """Profile for a speaker in the current session."""

    label: str
    features: list[float] = field(default_factory=list)
    count: int = 0


class SimpleSpeakerBackend:
    """Simple session-based speaker identification.

    Tracks speakers per session using simple audio features (energy, spectral
    centroid, zero-crossing rate). Assigns speaker labels (Speaker 1, Speaker 2, ...)
    based on feature similarity.

    Not persistent across sessions - each new backend instance starts fresh.
    """

    # Maximum number of speakers to track in a session
    MAX_SPEAKERS: ClassVar[int] = 10

    # Similarity threshold for matching speakers (cosine similarity)
    SIMILARITY_THRESHOLD: ClassVar[float] = 0.75

    def __init__(self) -> None:
        self._speakers: dict[int, SpeakerProfile] = {}
        self._next_speaker_id: int = 1
        self._min_utterance_duration: float = 0.5  # seconds

    def reset(self) -> None:
        """Clear all speaker profiles for a new session."""
        self._speakers.clear()
        self._next_speaker_id = 1

    def set_min_utterance_duration(self, seconds: float) -> None:
        """Set minimum utterance duration for identification."""
        self._min_utterance_duration = max(0.1, seconds)

    @classmethod
    def available(cls) -> bool:
        """Always available - no external dependencies."""
        return True

    def _extract_features(self, audio: bytes, sample_rate: int = 16000) -> list[float]:
        """Extract simple audio features from PCM16 audio.

        Returns:
            List of features: [rms_energy, zero_crossing_rate, spectral_centroid_approx]
        """
        if not audio:
            return [0.0, 0.0, 0.0]

        # Convert bytes to int16 samples
        samples = [
            int.from_bytes(audio[i : i + 2], "little", signed=True)
            for i in range(0, len(audio), 2)
        ]

        if len(samples) < 2:
            return [0.0, 0.0, 0.0]

        # RMS energy
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0

        # Zero-crossing rate
        zero_crossings = sum(
            1 for i in range(1, len(samples)) if samples[i] * samples[i - 1] < 0
        )
        zcr = zero_crossings / len(samples)

        # Spectral centroid approximation (using FFT would be more accurate,
        # but this is a simple approximation based on frequency content)
        # Use a simple high-frequency energy ratio
        high_freq_energy = sum(
            s * s for i, s in enumerate(samples) if i % 4 == 0
        ) / max(1, len(samples) // 4)
        total_energy = sum(s * s for s in samples) / max(1, len(samples))
        spectral_centroid = high_freq_energy / max(total_energy, 1e-10)

        return [rms, zcr, spectral_centroid]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two feature vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def identify(self, audio: bytes, sample_rate: int = 16000) -> str:
        """Identify speaker for an audio segment.

        Args:
            audio: PCM16 mono audio bytes.
            sample_rate: Sample rate in Hz (default 16000).

        Returns:
            Speaker label (e.g., "Speaker 1", "Speaker 2").
        """
        # Skip very short utterances
        duration = len(audio) / (sample_rate * 2)
        if duration < self._min_utterance_duration:
            # Return unknown speaker for very short segments
            return "Speaker ?"

        features = self._extract_features(audio, sample_rate)

        # Try to match with existing speakers
        best_speaker_id: int | None = None
        best_similarity: float = 0.0

        for speaker_id, profile in self._speakers.items():
            # Compute average features for this speaker
            if profile.features:
                avg_features = [
                    sum(profile.features[i :: len(features)]) / profile.count
                    for i in range(len(features))
                ]
                similarity = self._cosine_similarity(features, avg_features)
                if similarity > best_similarity and similarity >= self.SIMILARITY_THRESHOLD:
                    best_similarity = similarity
                    best_speaker_id = speaker_id

        if best_speaker_id is not None:
            # Update speaker profile
            profile = self._speakers[best_speaker_id]
            profile.features.extend(features)
            profile.count += 1
            return profile.label

        # New speaker
        if self._next_speaker_id > self.MAX_SPEAKERS:
            # Fallback to Speaker 1 if too many speakers
            return "Speaker 1"

        label = f"Speaker {self._next_speaker_id}"
        profile = SpeakerProfile(label=label, features=features, count=1)
        self._speakers[self._next_speaker_id] = profile
        self._next_speaker_id += 1
        return label


# Default backend instance
_default_speaker_backend: SimpleSpeakerBackend | None = None


def get_speaker_backend() -> SimpleSpeakerBackend:
    """Get or create the default speaker backend."""
    global _default_speaker_backend
    if _default_speaker_backend is None:
        _default_speaker_backend = SimpleSpeakerBackend()
    return _default_speaker_backend


def identify_speaker(audio: bytes, sample_rate: int = 16000) -> str:
    """Convenience function to identify speaker using the default backend."""
    return get_speaker_backend().identify(audio, sample_rate)


def reset_speaker_backend() -> None:
    """Reset the default speaker backend for a new session."""
    global _default_speaker_backend
    if _default_speaker_backend is not None:
        _default_speaker_backend.reset()
