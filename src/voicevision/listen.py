"""Listen mode: VAD + STT for continuous dictation.

Provides voicevision-listen command for push-to-talk or continuous dictation.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

from voicevision.backends.vad import WebrtcVadBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.core.cancellation import CancellationToken
from voicevision.core.protocols import VADProvider
from voicevision.errors import AudioDeviceError


@dataclass
class AudioChunk:
    """A chunk of audio data with timing."""
    data: bytes
    timestamp: float
    is_final: bool = False


class AudioBuffer:
    """Thread-safe circular audio buffer for pre-roll and streaming."""

    def __init__(self, capacity_frames: int, frame_bytes: int) -> None:
        self._capacity_bytes = capacity_frames * frame_bytes
        self._frame_bytes = frame_bytes
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._start_time: float | None = None

    def write(self, data: bytes, timestamp: float) -> None:
        """Write audio data to buffer."""
        with self._lock:
            if self._start_time is None:
                self._start_time = timestamp
            self._buffer.extend(data)
            # Trim to capacity
            if len(self._buffer) > self._capacity_bytes:
                excess = len(self._buffer) - self._capacity_bytes
                self._buffer = self._buffer[excess:]

    def read_all(self) -> bytes:
        """Read all buffered data and clear buffer."""
        with self._lock:
            data = bytes(self._buffer)
            self._buffer.clear()
            return data

    def read_last(self, duration_ms: int, frame_bytes: int) -> bytes:
        """Read last N milliseconds of audio."""
        bytes_needed = (duration_ms // 30) * self._frame_bytes
        with self._lock:
            if len(self._buffer) <= bytes_needed:
                return bytes(self._buffer)
            return bytes(self._buffer[-bytes_needed:])


class ListenSession:
    """Manages a continuous listening session with VAD and STT."""

    def __init__(
        self,
        vad: VADProvider,
        stt: Any,
        *,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        pre_roll_ms: int = 500,
        vad_silence_ms: int = 500,
        vad_max_utterance_ms: int = 30000,
        stt_language: str = "en",
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        self._vad = vad
        self._stt = stt
        self._sample_rate = sample_rate
        self._frame_ms = frame_ms
        self._pre_roll_ms = pre_roll_ms
        self._stt_language = stt_language
        self._cancellation_token = cancellation_token or CancellationToken.none()

        # Audio parameters
        self._frame_bytes = (sample_rate * frame_ms // 1000) * 2
        self._frames_per_second = 1000 // frame_ms

        # VAD configuration
        self._vad_silence_frames = max(1, vad_silence_ms // frame_ms)
        self._vad_max_frames = vad_max_utterance_ms // frame_ms

        # Pre-roll buffer
        pre_roll_frames = pre_roll_ms // frame_ms
        self._pre_roll_buffer = AudioBuffer(pre_roll_frames, self._frame_bytes)

        # State
        self._running = False
        self._audio_queue: queue.Queue[AudioChunk] = queue.Queue()
        self._capture_thread: threading.Thread | None = None
        self._process_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the listening session."""
        if self._running:
            return
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._capture_thread.start()
        self._process_thread.start()

    def stop(self) -> None:
        """Stop the listening session."""
        self._running = False
        self._cancellation_token.cancel()
        if self._capture_thread:
            self._capture_thread.join(timeout=1.0)
        if self._process_thread:
            self._process_thread.join(timeout=1.0)

    def __enter__(self) -> ListenSession:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _capture_loop(self) -> None:
        """Capture audio from microphone."""
        try:
            import sounddevice as sd
        except ImportError as err:
            raise AudioDeviceError(
                "sounddevice not installed. Install with: pip install sounddevice"
            ) from err

        def callback(indata: Any, frames: int, time: Any, status: Any) -> None:
            if not self._running:
                raise sd.CallbackAbort
            timestamp = time.time()
            self._audio_queue.put(AudioChunk(data=bytes(indata), timestamp=timestamp))

        with sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self._frame_bytes // 2,
            callback=callback,
        ):
            while self._running:
                time.sleep(0.1)

    def _process_loop(self) -> None:
        """Process audio chunks: VAD -> buffer -> STT."""
        vad = self._vad
        silence_frames = 0
        frames_in_utterance = 0
        in_utterance = False
        utterance_frames: list[bytes] = []

        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._cancellation_token.throw_if_cancelled()

            # Write to pre-roll buffer
            self._pre_roll_buffer.write(chunk.data, chunk.timestamp)

            # VAD processing
            is_speech = vad.process_frame(chunk.data)

            if is_speech:
                if not in_utterance:
                    # Start new utterance
                    in_utterance = True
                    utterance_frames = []
                    # Add pre-roll
                    pre_roll = self._pre_roll_buffer.read_all()
                    if pre_roll:
                        utterance_frames.append(pre_roll)
                    silence_frames = 0
                    frames_in_utterance = 1
                else:
                    frames_in_utterance += 1
                    silence_frames = 0

                utterance_frames.append(chunk.data)

                # Runaway protection
                max_frames = (
                    vad.max_utterance_ms // vad.frame_ms
                    if hasattr(vad, "frame_ms")
                    else 1000
                )
                if frames_in_utterance >= max_frames:
                    # Force end utterance
                    self._process_utterance(utterance_frames)
                    in_utterance = False
                    utterance_frames = []
                    silence_frames = 0
                    frames_in_utterance = 0

            else:
                if in_utterance:
                    silence_frames += 1
                    utterance_frames.append(chunk.data)
                    if silence_frames >= self._vad_silence_frames:
                        # End utterance
                        self._process_utterance(utterance_frames)
                        in_utterance = False
                        utterance_frames = []
                        silence_frames = 0
                        frames_in_utterance = 0
                # Else: silence outside utterance, ignore

    def _process_utterance(self, frames: list[bytes]) -> None:
        """Process a complete utterance through STT."""
        if not frames:
            return

        audio = b"".join(frames)
        if not audio:
            return

        # Transcribe
        try:
            transcript = self._stt.transcribe(audio, language=self._stt_language)
        except Exception:
            return

        if transcript.strip():
            print(f"> {transcript}")


def main(
    *,
    sample_rate: int = 16000,
    vad_aggressiveness: int = 2,
    vad_silence_ms: int = 500,
    vad_max_utterance_ms: int = 30000,
    stt_model: str = "",
    stt_language: str = "en",
    pre_roll_ms: int = 500,
    use_adaptive_vad: bool = False,
) -> None:
    """Main entry point for voicevision-listen."""
    if not stt_model:
        raise ValueError("stt_model is required")

    # Initialize backends
    stt = WhisperCppBackend(model=stt_model, language=stt_language)


    if use_adaptive_vad:
        from voicevision.backends.adaptive_vad import AdaptiveVadBackend
        vad: VADProvider = AdaptiveVadBackend(  # type: ignore[assignment]
            sample_rate=sample_rate,
            frame_ms=30,
            noise_percentile=10,
            sensitivity=2.0,
        )
    else:
        vad = WebrtcVadBackend(  # type: ignore[assignment]
            aggressiveness=vad_aggressiveness,
            sample_rate=sample_rate,
            silence_ms=vad_silence_ms,
            max_utterance_ms=vad_max_utterance_ms,
        )

    print("Listening... Press Ctrl+C to stop")
    with ListenSession(
        vad=vad,
        stt=stt,
        sample_rate=sample_rate,
        pre_roll_ms=pre_roll_ms,
        vad_silence_ms=vad_silence_ms,
        vad_max_utterance_ms=vad_max_utterance_ms,
        stt_language=stt_language,
    ):
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped")

