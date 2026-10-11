"""Voice activity detection via webrtcvad (ADR-001).

webrtcvad is a pure Python wrapper around WebRTC's VAD, no torch, ~1 MB wheel.
Operates on 30 ms frames at 8/16/32/48 kHz.
"""

from __future__ import annotations

import shutil
from typing import ClassVar, Iterator, Tuple

from voicevision.backends.subprocess_backend import SubprocessBackend
from voicevision.errors import BackendExecutionError, BackendNotAvailableError


class WebrtcVadBackend:
    """Segment a PCM16 stream into utterances using WebRTC VAD.

    Does NOT perform STT or TTS — only segmentation. Returns utterance
    boundaries as (start_offset, end_offset) in bytes. The caller decides
    what to do with each utterance (e.g., pass to STT).
    """

    # webrtcvad is a pure Python package; the import itself is the probe.
    install_hint: ClassVar[str] = "pip install webrtcvad-wheels"

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

    def segment(self, pcm: bytes) -> Iterator[Tuple[int, int]]:
        """Segment PCM16 audio into utterance byte ranges.

        Args:
            pcm: Raw PCM16 mono audio at the configured sample rate.

        Yields:
            (start_byte, end_byte) pairs for each detected utterance.
            Offsets are byte offsets into the input `pcm`.

        Raises:
            ValueError: if pcm length is not a multiple of frame_bytes.
        """
        if len(pcm) % self._frame_bytes != 0:
            raise ValueError(
                f"PCM length {len(pcm)} not a multiple of frame size {self._frame_bytes}"
            )

        import webrtcvad

        vad = webrtcvad.Vad(self._aggressiveness)

        # Silence threshold: how many consecutive non-speech frames to close utterance
        silence_frames = max(1, self._silence_ms // 30)
        # Max utterance frames for runaway protection
        max_frames = self._max_utterance_ms // 30

        frame_count = len(pcm) // self._frame_bytes
        in_utterance = False
        utterance_start = 0
        silence_count = 0
        frames_in_utterance = 0

        for i in range(frame_count):
            start = i * self._frame_bytes
            frame = pcm[start:start + self._frame_bytes]
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
            yield (utterance_start, len(pcm))

    def __repr__(self) -> str:
        return (
            f"WebrtcVadBackend(aggressiveness={self._aggressiveness}, "
            f"sample_rate={self._sample_rate}, silence_ms={self._silence_ms})"
        )

    def close(self) -> None:
        """No resources to release — included for uniform backend interface."""
        pass