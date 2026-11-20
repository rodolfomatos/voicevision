"""T094 — full-duplex DSP, echo cancellation and barge-in latency.

No microphone or sounddevice is needed: a fake duplex stream drives the
callbacks, and synthetic signals exercise the real numpy DSP code.
"""

from __future__ import annotations

import builtins
import time
from typing import Any

import numpy as np
import pytest

from voicevision.backends.audio_duplex import (
    AudioProcessor,
    AutomaticGainControl,
    BargeInDetector,
    DuplexAudioSession,
    DuplexConfig,
    EchoCanceller,
    NoiseSuppressor,
    rms,
)
from voicevision.core.cancellation import CancellationToken
from voicevision.errors import AudioDeviceError

# -- helpers ----------------------------------------------------------------


def _pcm(samples: np.ndarray) -> bytes:
    return bytes((np.clip(samples, -1.0, 1.0) * 32768).astype("<i2").tobytes())


def _floats(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0


def _tone(seconds: float = 1.0, freq: float = 440.0, sample_rate: int = 16000) -> np.ndarray:
    positions = np.arange(int(seconds * sample_rate))
    return (0.5 * np.sin(2 * np.pi * freq * positions / sample_rate)).astype(np.float64)


def _causal_filter(signal: np.ndarray, taps: np.ndarray) -> np.ndarray:
    """Apply a causal FIR filter (output[k] = sum_i taps[i] * input[k-i])."""
    output = np.zeros_like(signal)
    for delay, coefficient in enumerate(taps):
        output[delay:] += coefficient * signal[: len(signal) - delay]
    return output


# -- config ------------------------------------------------------------------


class TestDuplexConfig:
    def test_defaults(self) -> None:
        config = DuplexConfig()
        assert config.sample_rate == 16000
        assert config.frame_ms == 10
        assert config.frame_samples == 160
        assert config.frame_bytes == 320
        assert config.aec_enabled and config.barge_in_enabled

    def test_custom_frame_size(self) -> None:
        config = DuplexConfig(frame_ms=20)
        assert config.frame_samples == 320

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"frame_ms": 0},
            {"sample_rate": -1},
            {"aec_filter_length": 0},
            {"aec_strength": 1.5},
            {"echo_suppression": -0.1},
            {"noise_suppression_strength": 2.0},
            {"agc_target_rms": 0},
            {"barge_in_threshold_db": -1},
        ],
    )
    def test_invalid_config_rejected(self, kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            DuplexConfig(**kwargs)


# -- echo cancellation -------------------------------------------------------


class TestEchoCanceller:
    def test_echo_return_loss_enhancement(self) -> None:
        """AEC must suppress a synthetic echo path by at least 12 dB (ERLE)."""
        rng = np.random.default_rng(42)
        reference = rng.uniform(-0.5, 0.5, size=16000)
        echo_path = np.array([0.6, -0.3, 0.15, -0.08, 0.04, -0.02])
        echo = _causal_filter(reference, echo_path)
        near_end = 0.02 * _tone(freq=220.0)
        mic = echo + near_end
        canceller = EchoCanceller(strength=0.7, filter_length=32, echo_suppression=0.0)

        output = np.concatenate(
            [
                _floats(canceller.process(_pcm(mic[i : i + 160]), _pcm(reference[i : i + 160])))
                for i in range(0, len(mic), 160)
            ]
        )
        erle = 10 * np.log10(np.sum(mic**2) / np.sum(output**2))
        assert erle > 12.0, f"ERLE too low: {erle:.2f} dB"

    def test_echo_suppression_reduces_residual(self) -> None:
        reference = _tone(freq=440.0)
        mic = reference.copy()
        strong = EchoCanceller(strength=0.5, echo_suppression=0.9)
        weak = EchoCanceller(strength=0.5, echo_suppression=0.0)
        out_strong = _floats(strong.process(_pcm(mic), _pcm(reference)))
        out_weak = _floats(weak.process(_pcm(mic), _pcm(reference)))
        assert rms(out_strong) < rms(out_weak)

    def test_disabled_is_passthrough(self) -> None:
        frame = _pcm(_tone(seconds=0.01))
        assert EchoCanceller(enabled=False).process(frame, frame) == frame

    def test_missing_reference_is_silence(self) -> None:
        frame = _pcm(_tone(seconds=0.01))
        assert len(EchoCanceller().process(frame)) == len(frame)

    def test_reset_clears_filter(self) -> None:
        canceller = EchoCanceller()
        frame = _pcm(_tone(seconds=0.01))
        canceller.process(frame, frame)
        canceller.reset()
        assert np.count_nonzero(canceller._weights) == 0

    @pytest.mark.parametrize("kwargs", [{"strength": 1.2}, {"filter_length": 0}])
    def test_invalid_parameters(self, kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            EchoCanceller(**kwargs)


# -- noise and gain ----------------------------------------------------------


class TestNoiseSuppressor:
    def test_attenuates_stationary_noise(self) -> None:
        rng = np.random.default_rng(7)
        noise = rng.normal(0, 0.05, size=1600)
        suppressor = NoiseSuppressor(strength=0.8)
        for i in range(0, len(noise), 160):
            suppressor.process(_pcm(noise[i : i + 160]))
        noisy = noise[-160:] + 0.2 * _tone(seconds=0.01, freq=300.0)
        output = _floats(suppressor.process(_pcm(noisy)))
        assert rms(output) < rms(noisy)

    def test_disabled_is_passthrough(self) -> None:
        frame = _pcm(_tone(seconds=0.01))
        assert NoiseSuppressor(enabled=False).process(frame) == frame

    def test_reset_clears_profile(self) -> None:
        suppressor = NoiseSuppressor()
        suppressor.process(_pcm(_tone(seconds=0.01)))
        suppressor.reset()
        assert suppressor._noise is None

    def test_invalid_strength(self) -> None:
        with pytest.raises(ValueError):
            NoiseSuppressor(strength=2.0)


class TestAutomaticGainControl:
    def test_raises_quiet_signal_toward_target(self) -> None:
        frame = _pcm(0.01 * _tone(seconds=0.01))
        agc = AutomaticGainControl(target_rms=0.15, max_gain=8.0)
        output = _floats(agc.process(frame))
        assert rms(output) > rms(_floats(frame))

    def test_gain_is_capped(self) -> None:
        agc = AutomaticGainControl(max_gain=2.0)
        for _ in range(20):
            agc.process(_pcm(0.001 * _tone(seconds=0.01)))
        assert agc.gain <= 2.0

    def test_disabled_is_passthrough(self) -> None:
        frame = _pcm(_tone(seconds=0.01))
        assert AutomaticGainControl(enabled=False).process(frame) == frame


class TestAudioProcessor:
    def test_chain_respects_toggles(self) -> None:
        config = DuplexConfig(
            aec_enabled=False, noise_suppression_enabled=False, agc_enabled=False
        )
        processor = AudioProcessor(config)
        frame = _pcm(_tone(seconds=0.01))
        assert processor.process(frame, frame) == frame

    def test_reset_delegates_to_all_stages(self) -> None:
        processor = AudioProcessor()
        processor.process(_pcm(_tone(seconds=0.01)))
        processor.reset()
        assert processor.gain_control.gain == 1.0
        assert processor.noise_suppressor._noise is None


# -- barge-in ----------------------------------------------------------------


class TestBargeInDetector:
    def test_silent_during_playback_does_not_interrupt(self) -> None:
        token = CancellationToken()
        detector = BargeInDetector(token=token)
        detector.set_playback(True)
        assert detector.process(_pcm(np.zeros(160))) is False
        assert token.cancelled is False

    def test_speech_during_playback_interrupts(self) -> None:
        token = CancellationToken()
        detector = BargeInDetector(token=token)
        detector.set_playback(True)
        assert detector.process(_pcm(0.5 * _tone(seconds=0.01))) is True
        assert token.cancelled is True
        assert detector.playback_active is False

    def test_speech_while_idle_does_not_interrupt(self) -> None:
        token = CancellationToken()
        detector = BargeInDetector(token=token)
        assert detector.process(_pcm(0.5 * _tone(seconds=0.01))) is False
        assert token.cancelled is False

    def test_listener_is_notified(self) -> None:
        notified: list[str] = []
        detector = BargeInDetector()
        detector.on_barge_in(lambda: notified.append("stop"))
        detector.set_playback(True)
        detector.process(_pcm(0.5 * _tone(seconds=0.01)))
        assert notified == ["stop"]

    def test_high_threshold_ignores_quiet_speech(self) -> None:
        detector = BargeInDetector(config=DuplexConfig(barge_in_threshold_db=60.0))
        detector.set_playback(True)
        assert detector.process(_pcm(0.01 * _tone(seconds=0.01))) is False

    def test_disabled_detector_never_interrupts(self) -> None:
        detector = BargeInDetector(config=DuplexConfig(barge_in_enabled=False))
        detector.set_playback(True)
        assert detector.process(_pcm(0.9 * _tone(seconds=0.01))) is False

    def test_interruption_latency_under_50ms(self) -> None:
        detector = BargeInDetector()
        detector.set_playback(True)
        speech = _pcm(0.5 * _tone(seconds=0.01))
        detector.begin_frame()
        started = time.perf_counter()
        assert detector.process(speech) is True
        elapsed = (time.perf_counter() - started) * 1000
        assert elapsed < 50.0
        assert detector.detection_latency_ms is not None
        assert detector.detection_latency_ms < 50.0


# -- duplex session ----------------------------------------------------------


class FakeStream:
    """Minimal sounddevice-style duplex stream for callback tests."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.frames = kwargs["blocksize"]
        self.started = False
        self.closed = False
        self.output: bytes = b""

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True

    def push(self, mic: bytes) -> None:
        outdata = np.zeros((self.frames, 1), dtype="<i2")
        indata = np.frombuffer(mic, dtype="<i2").reshape(-1, 1)
        self.callback(indata, outdata, self.frames, None, None)
        self.output = outdata.tobytes()


class TestDuplexAudioSession:
    @staticmethod
    def _session(**kwargs: Any) -> tuple[DuplexAudioSession, FakeStream]:
        streams: list[FakeStream] = []

        def factory(**factory_kwargs: Any) -> FakeStream:
            stream = FakeStream(**factory_kwargs)
            streams.append(stream)
            return stream

        session = DuplexAudioSession(stream_factory=factory, **kwargs)
        session.start()
        return session, streams[0]

    def test_duplex_callback_captures_and_plays(self) -> None:
        session, stream = self._session()
        session.play(_pcm(0.3 * _tone(seconds=0.02)))
        stream.push(_pcm(0.01 * _tone(seconds=0.01, freq=220.0)))
        captured = session.captured_now()
        assert len(captured) == 1
        assert len(captured[0]) == stream.frames * 2
        assert len(stream.output) == stream.frames * 2
        session.stop()
        assert not stream.started and stream.closed

    def test_barge_in_clears_playback_and_cancels(self) -> None:
        session, stream = self._session()
        session.play(_pcm(0.3 * _tone(seconds=0.05)))
        stream.push(_pcm(0.9 * _tone(seconds=0.01)))
        assert session.token.cancelled is True
        assert session.captured_now()

    def test_idempotent_start(self) -> None:
        session, stream = self._session()
        session.start()
        assert session._stream is stream

    def test_missing_sounddevice_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_import = builtins.__import__

        def no_sounddevice(name: str, *args: object, **kwargs: object) -> Any:
            if name == "sounddevice":
                raise ImportError("sounddevice is not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_sounddevice)
        with pytest.raises(AudioDeviceError, match="sounddevice"):
            DuplexAudioSession().start()
