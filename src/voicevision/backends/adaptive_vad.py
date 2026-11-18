"""Adaptive Voice Activity Detection via percentile-based noise floor estimation.

Ported from Hex (anomalyco/hex) crates/capture/src/transcribe.rs.
Uses speech_islands algorithm with adaptive threshold based on noise floor.

Implements VADProvider protocol (M1).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import ClassVar

from voicevision.core.protocols import ProviderCapabilities, ProviderLifecycle


class AdaptiveVadBackend:
    """Adaptive VAD using percentile-based noise floor estimation.

    Implements VADProvider protocol.

    The algorithm:
    1. Estimates noise floor from audio using percentile (default 10th)
    2. Sets threshold as noise_floor * sensitivity_multiplier
    3. Detects speech islands above threshold
    4. Merges nearby islands (gap < MERGE_GAP_MS)
    5. Filters digital silence (RMS < ISLAND_SILENCE_RMS)

    Ported from Hex's speech_islands algorithm.
    """

    #: Hex constants
    MERGE_GAP_MS: ClassVar[int] = 700
    ISLAND_SILENCE_RMS: ClassVar[float] = 0.0005

    #: Default noise percentile for noise floor estimation
    DEFAULT_NOISE_PERCENTILE: ClassVar[int] = 10

    _install_hint: ClassVar[str] = "Built-in: no installation required"

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        noise_percentile: int = 10,
        sensitivity: float = 2.0,
    ) -> None:
        if not 0 < noise_percentile < 100:
            raise ValueError("noise_percentile must be 1-99")
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError("sample_rate must be 8000, 16000, 32000, or 48000")
        if frame_ms <= 0:
            raise ValueError("frame_ms must be positive")

        self._sample_rate = sample_rate
        self._frame_ms = frame_ms
        self._noise_percentile = noise_percentile
        self._sensitivity = sensitivity

        # Frame size in bytes: frame_ms at sample_rate, 16-bit mono
        self._frame_bytes = (sample_rate * frame_ms // 1000) * 2
        self._frame_samples = sample_rate * frame_ms // 1000

    @classmethod
    def available(cls) -> bool:
        return True

    @classmethod
    def install_hint(cls) -> str:
        return cls._install_hint

    # -- VADProvider protocol --------------------------------------------------

    def process_frame(
        self,
        frame: bytes,
        *,
        token: CancellationToken | None = None,
    ) -> bool:
        """Process a single audio frame for speech detection.

        Args:
            frame: Audio frame (frame_ms at sample_rate, 16-bit mono).
            token: Optional cancellation token.

        Returns:
            True if speech detected in frame.
        """
        if token is not None:
            token.throw_if_cancelled()

        if len(frame) != self._frame_bytes:
            raise ValueError(f"Frame must be {self._frame_bytes} bytes, got {len(frame)}")

        # Simple energy-based detection (fallback)
        rms = self._compute_rms(frame)
        return rms > self.ISLAND_SILENCE_RMS

    def segment(
        self,
        audio: bytes,
        *,
        token: CancellationToken | None = None,
    ) -> Generator[tuple[int, int], None, None]:
        """Segment audio into utterance byte ranges using adaptive speech_islands.

        Args:
            audio: Complete PCM16 audio.
            token: Optional cancellation token.

        Yields:
            (start_byte, end_byte) pairs for each utterance.

        Raises:
            ValueError: if pcm length is not a multiple of frame_bytes.
        """
        if token is not None:
            token.throw_if_cancelled()

        if len(audio) % self._frame_bytes != 0:
            raise ValueError(
                f"PCM length {len(audio)} not a multiple of frame size {self._frame_bytes}"
            )

        # Compute RMS energy per frame
        frame_count = len(audio) // self._frame_bytes
        rms_values = []

        for i in range(frame_count):
            if token is not None:
                token.throw_if_cancelled()

            start = i * self._frame_bytes
            frame = audio[start : start + self._frame_bytes]
            rms = self._compute_rms(frame)
            rms_values.append(rms)

        # Estimate noise floor using percentile
        noise_floor = self._percentile(rms_values, self._noise_percentile)
        threshold = noise_floor * self._sensitivity

        # Detect speech islands above threshold
        islands = self._detect_islands(rms_values, threshold)

        # Merge nearby islands
        islands = self._merge_islands(islands)

        # Filter digital silence
        islands = self._filter_silence(islands, rms_values)

        # Convert frame indices to byte offsets
        for start_frame, end_frame in islands:
            start_byte = start_frame * self._frame_bytes
            end_byte = end_frame * self._frame_bytes
            yield (start_byte, end_byte)

    @property
    def frame_bytes(self) -> int:
        return self._frame_bytes

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    # -- Provider protocol -----------------------------------------------------

    @property
    def name(self) -> str:
        return "adaptive"

    @property
    def modality(self) -> str:
        return "vad"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=True,
            languages=frozenset(),
            models=frozenset(),
            max_concurrent=10,
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

    # -- Internal methods ------------------------------------------------------

    def _compute_rms(self, frame: bytes) -> float:
        """Compute RMS energy of a frame (0.0 to 1.0)."""
        if not frame:
            return 0.0

        # Convert bytes to int16 samples
        samples = [
            int.from_bytes(frame[i : i + 2], "little", signed=True)
            for i in range(0, len(frame), 2)
        ]

        if not samples:
            return 0.0

        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        return float(rms / 32768.0)  # Normalize to 0.0-1.0

    def _percentile(self, values: list[float], percentile: int) -> float:
        """Compute percentile of values."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        index = max(0, min(index, len(sorted_values) - 1))
        return sorted_values[index]

    def _detect_islands(self, rms_values: list[float], threshold: float) -> list[tuple[int, int]]:
        """Detect speech islands above threshold.

        Returns:
            List of (start_frame, end_frame) tuples (end exclusive).
        """
        islands = []
        in_island = False
        island_start = 0

        for i, rms in enumerate(rms_values):
            is_speech = rms > threshold

            if is_speech and not in_island:
                in_island = True
                island_start = i
            elif not is_speech and in_island:
                in_island = False
                islands.append((island_start, i))

        # Handle island extending to end
        if in_island:
            islands.append((island_start, len(rms_values)))

        return islands

    def _merge_islands(self, islands: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Merge islands separated by less than MERGE_GAP_MS."""
        if not islands:
            return []

        merged = [islands[0]]
        gap_frames = self.MERGE_GAP_MS // self._frame_ms

        for start, end in islands[1:]:
            last_start, last_end = merged[-1]
            if start - last_end <= gap_frames:
                # Merge with previous island
                merged[-1] = (last_start, end)
            else:
                merged.append((start, end))

        return merged

    def _filter_silence(
        self,
        islands: list[tuple[int, int]],
        rms_values: list[float],
    ) -> list[tuple[int, int]]:
        """Filter out islands that are essentially digital silence."""
        filtered = []
        for start, end in islands:
            # Check average RMS of island
            island_rms = rms_values[start:end]
            avg_rms = sum(island_rms) / len(island_rms)
            if avg_rms > self.ISLAND_SILENCE_RMS:
                filtered.append((start, end))
        return filtered


# Forward reference for type hints
class CancellationToken:
    """Forward reference."""
    def throw_if_cancelled(self) -> None: ...
