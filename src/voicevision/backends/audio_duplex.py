"""Full-duplex audio processing: capture and playback at the same time (T094.

The DSP is implemented with numpy so it runs on CPU without native extras.
``sounddevice`` is imported only when a real duplex stream is opened; tests
inject a ``stream_factory`` instead. The building blocks are deliberately
small and composable:

* :class:`EchoCanceller` — block NLMS adaptive filter plus residual suppression.
* :class:`NoiseSuppressor` — spectral gate with a running noise profile.
* :class:`AutomaticGainControl` — smoothed RMS target with a gain ceiling.
* :class:`BargeInDetector` — triggers cancellation on speech during playback.
* :class:`DuplexAudioSession` — sounddevice duplex loop feeding cleaned audio.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from voicevision.core.cancellation import CancellationToken

#: Convert float samples in [-1, 1] to PCM16 bytes and back.
_SCALE = 32768.0


def _to_float(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype="<i2").astype(np.float64) / _SCALE


def _to_pcm(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0 - 1.0 / _SCALE)
    return bytes((clipped * _SCALE).astype("<i2").tobytes())


def rms(samples: np.ndarray) -> float:
    """Root-mean-square of a sample block (0.0 for an empty block)."""
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


@dataclass
class DuplexConfig:
    """Tunable parameters for the full-duplex audio path."""

    sample_rate: int = 16000
    frame_ms: int = 10
    # Acoustic echo cancellation
    aec_enabled: bool = True
    aec_strength: float = 0.5
    aec_filter_length: int = 128
    echo_suppression: float = 0.5
    # Noise suppression and gain control
    noise_suppression_enabled: bool = True
    noise_suppression_strength: float = 0.5
    agc_enabled: bool = True
    agc_target_rms: float = 0.15
    agc_max_gain: float = 4.0
    # Barge-in
    barge_in_enabled: bool = True
    barge_in_threshold_db: float = 12.0

    def __post_init__(self) -> None:
        if self.sample_rate <= 0 or self.frame_ms <= 0:
            raise ValueError("sample_rate and frame_ms must be positive")
        if self.aec_filter_length <= 0:
            raise ValueError("aec_filter_length must be positive")
        for name in ("aec_strength", "echo_suppression", "noise_suppression_strength"):
            if not 0.0 <= float(getattr(self, name)) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.agc_target_rms <= 0 or self.agc_max_gain <= 0:
            raise ValueError("AGC target and max gain must be positive")
        if self.barge_in_threshold_db < 0:
            raise ValueError("barge_in_threshold_db must be non-negative")

    @property
    def frame_samples(self) -> int:
        return max(1, self.sample_rate * self.frame_ms // 1000)

    @property
    def frame_bytes(self) -> int:
        return self.frame_samples * 2


class EchoCanceller:
    """Block NLMS acoustic echo canceller.

    ``mic`` is the microphone signal (far-end echo + near-end speech) and
    ``reference`` is the playback signal. The adaptive filter models the echo
    path; its output is subtracted from ``mic``. ``strength`` maps to the NLMS
    step size, and ``echo_suppression`` attenuates the residual where the
    reference is active.
    """

    def __init__(
        self,
        *,
        strength: float = 0.5,
        filter_length: int = 128,
        echo_suppression: float = 0.5,
        enabled: bool = True,
    ) -> None:
        if not 0.0 <= strength <= 1.0 or not 0.0 <= echo_suppression <= 1.0:
            raise ValueError("strength and echo_suppression must be between 0 and 1")
        if filter_length <= 0:
            raise ValueError("filter_length must be positive")
        self.strength = strength
        self.echo_suppression = echo_suppression
        self.enabled = enabled
        self._length = filter_length
        self._weights = np.zeros(filter_length, dtype=np.float64)
        self._history = np.zeros(max(0, filter_length - 1), dtype=np.float64)

    def reset(self) -> None:
        self._weights.fill(0.0)
        self._history.fill(0.0)

    def process(self, mic: bytes, reference: bytes | None = None) -> bytes:
        if not self.enabled or not mic:
            return mic
        mic_samples = _to_float(mic)
        if reference is None or len(reference) < 2:
            reference = b"\x00" * (len(mic_samples) * 2)
        ref_samples = _to_float(reference)
        count = min(len(mic_samples), len(ref_samples))
        if count == 0:
            return mic
        mic_samples = mic_samples[:count]
        ref_samples = ref_samples[:count]

        padded = np.concatenate((self._history, ref_samples))
        windows = np.lib.stride_tricks.sliding_window_view(padded, self._length)
        error = np.empty(count, dtype=np.float64)

        # Per-sample NLMS: normalising each tap vector by its own energy makes
        # convergence fast and remains stable even for correlated far-end audio
        # (e.g. a pure tone, where a fast *block* step would diverge).
        mu = 0.05 + 0.9 * self.strength
        for i in range(count):
            x = windows[i]
            e = mic_samples[i] - float(x @ self._weights)
            error[i] = e
            self._weights += (mu / (float(x @ x) + 1e-8)) * x * e
        self._history = padded[-(self._length - 1) :] if self._length > 1 else np.array([])

        if self.echo_suppression and count:
            ref_level = np.sqrt(np.mean(windows * windows, axis=1))
            active = ref_level > 1e-4
            factor = 1.0 - self.echo_suppression * 0.9
            error = np.where(active, error * factor, error)

        return _to_pcm(error)


class NoiseSuppressor:
    """Spectral gate with a running (minimum-statistics) noise profile."""

    def __init__(self, *, strength: float = 0.5, enabled: bool = True) -> None:
        if not 0.0 <= strength <= 1.0:
            raise ValueError("strength must be between 0 and 1")
        self.strength = strength
        self.enabled = enabled
        self._noise: np.ndarray | None = None

    def reset(self) -> None:
        self._noise = None

    def process(self, frame: bytes) -> bytes:
        if not self.enabled or not frame:
            return frame
        samples = _to_float(frame)
        spectrum = np.fft.rfft(samples)
        magnitude = np.abs(spectrum)
        if self._noise is None:
            self._noise = magnitude.copy()
        else:
            size = min(len(self._noise), len(magnitude))
            self._noise[:size] = np.minimum(self._noise[:size], magnitude[:size])
        # A higher strength raises the gate and lowers the residual floor.
        threshold = self._noise * (1.0 + 0.5 + 2.0 * self.strength)
        gain = np.clip((magnitude - threshold) / (magnitude + 1e-10), 1.0 - self.strength, 1.0)
        return _to_pcm(np.fft.irfft(spectrum * gain, n=len(samples)))


class AutomaticGainControl:
    """Smoothly drive signal RMS towards a target, with attack/release and a cap."""

    def __init__(
        self,
        *,
        target_rms: float = 0.15,
        max_gain: float = 4.0,
        enabled: bool = True,
    ) -> None:
        if target_rms <= 0 or max_gain <= 0:
            raise ValueError("target_rms and max_gain must be positive")
        self.target_rms = target_rms
        self.max_gain = max_gain
        self.enabled = enabled
        self.gain = 1.0

    def reset(self) -> None:
        self.gain = 1.0

    def process(self, frame: bytes) -> bytes:
        if not self.enabled or not frame:
            return frame
        samples = _to_float(frame)
        level = rms(samples)
        if level < 1e-6:
            return frame
        desired = float(np.clip(self.target_rms / level, 1.0 / self.max_gain, self.max_gain))
        alpha = 0.4 if desired > self.gain else 0.05  # fast attack, slow release
        self.gain += alpha * (desired - self.gain)
        return _to_pcm(samples * self.gain)


class AudioProcessor:
    """AEC → noise suppression → AGC, configured by :class:`DuplexConfig`."""

    def __init__(self, config: DuplexConfig | None = None) -> None:
        self.config = config or DuplexConfig()
        self.echo_canceller = EchoCanceller(
            strength=self.config.aec_strength,
            filter_length=self.config.aec_filter_length,
            echo_suppression=self.config.echo_suppression,
            enabled=self.config.aec_enabled,
        )
        self.noise_suppressor = NoiseSuppressor(
            strength=self.config.noise_suppression_strength,
            enabled=self.config.noise_suppression_enabled,
        )
        self.gain_control = AutomaticGainControl(
            target_rms=self.config.agc_target_rms,
            max_gain=self.config.agc_max_gain,
            enabled=self.config.agc_enabled,
        )

    def reset(self) -> None:
        self.echo_canceller.reset()
        self.noise_suppressor.reset()
        self.gain_control.reset()

    def process(self, mic: bytes, reference: bytes | None = None) -> bytes:
        """Return the cleaned microphone frame for capture/STT."""
        cleaned = self.echo_canceller.process(mic, reference)
        cleaned = self.noise_suppressor.process(cleaned)
        return self.gain_control.process(cleaned)


class BargeInDetector:
    """Detect near-end speech during playback and cancel the response token.

    With 10 ms frames the worst-case detection latency is one frame plus the
    processing time of :meth:`process`, comfortably inside the 50 ms budget.
    """

    def __init__(
        self,
        *,
        config: DuplexConfig | None = None,
        token: CancellationToken | None = None,
    ) -> None:
        self.config = config or DuplexConfig()
        self.token = token
        self._noise_floor = 1e-4
        self._playback_active = False
        self._listeners: list[Callable[[], None]] = []
        self._detected_at: float | None = None
        self._detection_latency_ms: float | None = None
        self._frame_started: float | None = None

    def on_barge_in(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def set_playback(self, active: bool) -> None:
        """Mark whether assistant audio is currently being played."""
        self._playback_active = active
        if not active:
            self._detected_at = None

    @property
    def playback_active(self) -> bool:
        return self._playback_active

    @property
    def detection_latency_ms(self) -> float | None:
        """Wall-clock time from the triggering frame to cancellation (T094)."""
        return self._detection_latency_ms

    def begin_frame(self) -> None:
        """Mark frame arrival so detection latency can be measured."""
        self._frame_started = time.perf_counter()

    def process(self, mic_frame: bytes) -> bool:
        """Return True (and notify/cancel) when speech interrupts playback."""
        if not self.config.barge_in_enabled or not mic_frame:
            return False
        level = rms(_to_float(mic_frame))
        if not self._playback_active:
            # Track the noise floor only while the assistant is silent.
            self._noise_floor = 0.98 * self._noise_floor + 0.02 * level
            return False
        threshold = self._noise_floor * 10 ** (self.config.barge_in_threshold_db / 20)
        if level <= threshold:
            return False
        started = self._frame_started
        self._detected_at = time.perf_counter()
        if started is not None:
            self._detection_latency_ms = (self._detected_at - started) * 1000
        self._playback_active = False
        if self.token is not None:
            self.token.cancel()
        for listener in self._listeners:
            listener()
        return True


@dataclass
class DuplexAudioSession:
    """Concurrent capture and playback via a sounddevice-style duplex stream.

    Pass ``stream_factory`` to inject a fake stream in tests. A factory takes
    ``(samplerate, blocksize, dtype, callback)`` and returns an object with
    ``start()``, ``stop()`` and ``close()`` methods.
    """

    config: DuplexConfig = field(default_factory=DuplexConfig)
    token: CancellationToken = field(default_factory=CancellationToken)
    stream_factory: Callable[..., Any] | None = None
    processor: AudioProcessor | None = None
    detector: BargeInDetector | None = None

    def __post_init__(self) -> None:
        self.processor = self.processor or AudioProcessor(self.config)
        self.detector = self.detector or BargeInDetector(config=self.config, token=self.token)
        self._captured: queue.Queue[bytes] = queue.Queue()
        self._playback: bytearray = bytearray()
        self._lock = threading.Lock()
        self._stream: Any | None = None

    # -- stream lifecycle ----------------------------------------------------

    def start(self) -> None:
        """Open the duplex stream. Imports sounddevice only at this point."""
        if self._stream is not None:
            return
        factory = self.stream_factory
        if factory is None:
            try:
                import sounddevice as sd
            except ImportError as exc:
                from voicevision.errors import AudioDeviceError

                raise AudioDeviceError(
                    "sounddevice not installed. Install with: pip install sounddevice"
                ) from exc
            factory = sd.Stream
        self._stream = factory(
            samplerate=self.config.sample_rate,
            blocksize=self.config.frame_samples,
            dtype="int16",
            channels=1,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop and close the stream, cancelling any in-flight response."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        # Wake any consumer blocked in captured_frames() so threads can exit.
        self._captured.put(b"")
        self.token.cancel()

    def __enter__(self) -> DuplexAudioSession:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    # -- duplex callback -----------------------------------------------------

    def _callback(
        self, indata: Any, outdata: Any, frames: int, time_info: Any, status: Any
    ) -> None:
        """sounddevice callback: clean input, fill output with queued playback."""
        mic = bytes(np.asarray(indata).reshape(-1)[:frames].view("<i2").tobytes())
        frame_bytes = frames * 2
        with self._lock:
            reference = bytes(self._playback[:frame_bytes])
            if reference:
                del self._playback[:frame_bytes]
            self.detector.begin_frame()  # type: ignore[union-attr]
        # Playback being drained means the assistant is speaking: arm barge-in.
        if reference:
            self.detector.set_playback(True)  # type: ignore[union-attr]
        reference = reference.ljust(frame_bytes, b"\x00")
        cleaned = self.processor.process(mic, reference)  # type: ignore[union-attr]
        self._captured.put(cleaned)
        if self.detector.process(cleaned):  # type: ignore[union-attr]
            with self._lock:
                self._playback.clear()
        # Always emit something: silence when there is no queued playback.
        outdata[:] = np.frombuffer(reference, dtype="<i2").reshape(-1, 1)

    # -- public API ----------------------------------------------------------

    def play(self, pcm: bytes) -> None:
        """Queue PCM16 playback audio (appended after any pending audio)."""
        with self._lock:
            self._playback.extend(pcm)

    def captured_frames(self) -> Iterator[bytes]:
        """Yield cleaned microphone frames as they arrive (blocks)."""
        while True:
            frame = self._captured.get()
            if not frame:
                return
            yield frame

    def captured_now(self) -> list[bytes]:
        """Drain all currently available captured frames (non-blocking)."""
        frames: list[bytes] = []
        while True:
            try:
                frames.append(self._captured.get_nowait())
            except queue.Empty:
                return frames


__all__ = [
    "AutomaticGainControl",
    "BargeInDetector",
    "DuplexAudioSession",
    "DuplexConfig",
    "EchoCanceller",
    "NoiseSuppressor",
    "AudioProcessor",
    "rms",
]
