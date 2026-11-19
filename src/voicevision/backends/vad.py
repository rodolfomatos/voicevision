"""Voice activity detection via webrtcvad (ADR-001).

webrtcvad is a pure Python wrapper around WebRTC's VAD, no torch, ~1 MB wheel.
Operates on 30 ms frames at 8/16/32/48 kHz.

Implements VADProvider protocol (M1).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from voicevision.core.protocols import ProviderCapabilities, ProviderLifecycle

if TYPE_CHECKING:
    import webrtcvad


class WebrtcVadBackend:
    """Segment a PCM16 stream into utterances using WebRTC VAD.

    Implements VADProvider protocol.

    Does NOT perform STT or TTS — only segmentation. Returns utterance
    boundaries as (start_offset, end_offset) in bytes. The caller decides
    what to do with each utterance (e.g., pass to STT).
    """

    # webrtcvad is a pure Python package; the import itself is the probe.

    @classmethod
    def install_hint(cls) -> str:
        return "pip install webrtcvad-wheels"

    def __init__(
        self,
        *,
        aggressiveness: int = 2,
        sample_rate: int = 16000,
        silence_ms: int = 500,
        max_utterance_ms: int = 30000,
    ) -> None:
        if not 0 <= aggressiveness <= 3:
            raise ValueError("aggressiveness must be 0-3")
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError("sample_rate must be 8000, 16000, 32000, or 48000")
        if silence_ms <= 0:
            raise ValueError("silence_ms must be positive")
        if max_utterance_ms <= 0:
            raise ValueError("max_utterance_ms must be positive")

        self._aggressiveness = aggressiveness
        self._sample_rate = sample_rate
        self._silence_ms = silence_ms
        self._max_utterance_ms = max_utterance_ms

        # Frame size in bytes: 30 ms at sample_rate, 16-bit mono
        self._frame_bytes = (sample_rate * 30 // 1000) * 2

    @classmethod
    def available(cls) -> bool:
        try:
            import webrtcvad  # noqa: F401
        except ImportError:
            return False
        return True

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
        if token is not None:
            token.throw_if_cancelled()

        if len(frame) != self._frame_bytes:
            raise ValueError(f"Frame must be {self._frame_bytes} bytes, got {len(frame)}")

        import webrtcvad

        vad = webrtcvad.Vad(self._aggressiveness)
        result: bool = vad.is_speech(frame, self._sample_rate)
        return result

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

        Raises:
            ValueError: if pcm length is not a multiple of frame_bytes.
        """
        if token is not None:
            token.throw_if_cancelled()

        if len(audio) % self._frame_bytes != 0:
            raise ValueError(
                f"PCM length {len(audio)} not a multiple of frame size {self._frame_bytes}"
            )

        import webrtcvad

        vad = webrtcvad.Vad(self._aggressiveness)

        # Silence threshold: how many consecutive non-speech frames to close utterance
        silence_frames = max(1, self._silence_ms // 30)
        # Max utterance frames for runaway protection
        max_frames = self._max_utterance_ms // 30

        frame_count = len(audio) // self._frame_bytes
        return self._segment_audio(
            audio, vad, frame_count, silence_frames, max_frames, token
        )

    def _segment_audio(
        self,
        audio: bytes,
        vad: webrtcvad.Vad,  # avoid import at top level
        frame_count: int,
        silence_frames: int,
        max_frames: int,
        token: CancellationToken | None,
    ) -> Generator[tuple[int, int], None, None]:
        """Process frames and yield utterance boundaries."""
        in_utterance = False
        utterance_start = 0
        silence_count = 0
        frames_in_utterance = 0

        for i in range(frame_count):
            if token is not None:
                token.throw_if_cancelled()

            start = i * self._frame_bytes
            frame = audio[start : start + self._frame_bytes]
            is_speech = vad.is_speech(frame, self._sample_rate)

            if is_speech:
                if not in_utterance:
                    in_utterance = True
                    utterance_start = i * self._frame_bytes
                    silence_count = 0
                    frames_in_utterance = 1
                else:
                    frames_in_utterance += 1
                    silence_count = 0

                # Runaway protection: force-close if utterance too long
                if frames_in_utterance >= max_frames:
                    end = (i + 1) * self._frame_bytes
                    yield (utterance_start, end)
                    in_utterance = False
                    frames_in_utterance = 0
                    silence_count = 0
            else:
                if in_utterance:
                    silence_count += 1
                    if silence_count >= silence_frames:
                        # Utterance ends at the START of the silence run
                        end = (i - silence_frames + 1) * self._frame_bytes
                        yield (utterance_start, end)
                        in_utterance = False
                        frames_in_utterance = 0
                        silence_count = 0

        # Stream ended while in utterance: emit final utterance
        if in_utterance:
            yield (utterance_start, len(audio))

    @property
    def frame_bytes(self) -> int:
        """Frame size in bytes for the configured sample rate."""
        return self._frame_bytes

    @property
    def frame_ms(self) -> int:
        """Frame duration in milliseconds."""
        return 30  # Fixed for WebRTC VAD

    @property
    def max_utterance_ms(self) -> int:
        """Maximum utterance duration in milliseconds."""
        return self._max_utterance_ms

    @property
    def sample_rate(self) -> int:
        """Sample rate in Hz."""
        return self._sample_rate

    # -- Provider protocol -----------------------------------------------------

    @property
    def name(self) -> str:
        return "webrtcvad"

    @property
    def modality(self) -> str:
        return "vad"

    def capabilities(self) -> ProviderCapabilities:
        from voicevision.core.protocols import ProviderCapabilities
        return ProviderCapabilities(
            streaming=True,
            languages=frozenset(),  # VAD is language-agnostic
            models=frozenset(),
            max_concurrent=10,
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

    def close(self) -> None:
        """No resources to release — included for uniform backend interface."""
        pass

    def __repr__(self) -> str:
        return (
            f"WebrtcVadBackend(aggressiveness={self._aggressiveness}, "
            f"sample_rate={self._sample_rate}, silence_ms={self._silence_ms})"
        )


# Forward reference for type hints
class CancellationToken:
    """Forward reference."""
    def throw_if_cancelled(self) -> None: ...
