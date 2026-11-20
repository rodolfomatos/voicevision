"""Tests for voicevision.listen — microphone → VAD → STT → text on stdout.

No real microphone, no sounddevice, no webrtcvad, and no whisper.cpp binary
are needed: everything is mocked or replaced with the fake child.
"""

from __future__ import annotations

import pytest

# -- main entry point --------------------------------------------------------


class TestMain:
    def test_missing_stt_model_raises_value_error(self) -> None:
        from voicevision.listen import main

        with pytest.raises(ValueError, match="stt_model is required"):
            main()

    def test_main_requires_stt_model(self) -> None:
        from voicevision.listen import main

        with pytest.raises(ValueError, match="stt_model is required"):
            main()


class TestSpeakerIntegration:
    """T092 — optional speaker labels are attached to transcriptions."""

    def test_utterance_is_labelled_with_speaker(self, capsys: pytest.CaptureFixture[str]) -> None:
        from voicevision.listen import ListenSession

        class FakeVAD:
            frame_ms = 30
            max_utterance_ms = 30000

            def process_frame(self, data: bytes) -> bool:
                return False

        class FakeSTT:
            def transcribe(self, audio: bytes, **kwargs: object) -> str:
                return "hello world"

        class FakeSpeaker:
            def identify(self, audio: bytes, **kwargs: object) -> str:
                return "Alice"

        session = ListenSession(
            vad=FakeVAD(),  # type: ignore[arg-type]
            stt=FakeSTT(),
            speaker=FakeSpeaker(),  # type: ignore[arg-type]
        )
        session._process_utterance([b"\x00\x00" * 100])
        assert "[Alice] > hello world" in capsys.readouterr().out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class FakeDuplexStream:
    """Minimal sounddevice-style duplex stream for ListenSession duplex tests."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.callback = kwargs["callback"]  # type: ignore[index]
        self.frames = kwargs["blocksize"]  # type: ignore[index]
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True

    def push(self, mic: bytes) -> None:
        import numpy as np

        outdata = np.zeros((self.frames, 1), dtype="<i2")
        indata = np.frombuffer(mic, dtype="<i2").reshape(-1, 1)
        self.callback(indata, outdata, self.frames, None, None)


class TestDuplexListen:
    """T094 — ListenSession captures through a duplex stream when configured."""

    @staticmethod
    def _fakes():
        class FakeVAD:
            frame_ms = 30
            max_utterance_ms = 30000

            def process_frame(self, data: bytes) -> bool:
                return False

        class FakeSTT:
            def transcribe(self, audio: bytes, **kwargs: object) -> str:
                return ""

        return FakeVAD(), FakeSTT()

    @staticmethod
    def _factory(streams: list[FakeDuplexStream]):
        def factory(**kwargs: object) -> FakeDuplexStream:
            stream = FakeDuplexStream(**kwargs)
            streams.append(stream)
            return stream

        return factory

    def test_duplex_session_created_with_config(self) -> None:
        from voicevision.backends.audio_duplex import DuplexConfig
        from voicevision.listen import ListenSession

        vad, stt = self._fakes()
        streams: list[FakeDuplexStream] = []
        session = ListenSession(
            vad=vad,  # type: ignore[arg-type]
            stt=stt,
            duplex_config=DuplexConfig(frame_ms=10),
            duplex_stream_factory=self._factory(streams),  # type: ignore[arg-type]
        )
        session.start()
        try:
            assert session._duplex_session is not None
            assert len(streams) == 1
            assert streams[0].kwargs["blocksize"] == 160
            assert streams[0].started
        finally:
            session.stop()
        assert streams[0].closed

    def test_play_requires_duplex_mode(self) -> None:
        from voicevision.listen import ListenSession

        vad, stt = self._fakes()
        session = ListenSession(vad=vad, stt=stt)  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="duplex"):
            session.play(b"\x00\x00" * 10)

    def test_play_queues_audio_in_duplex_mode(self) -> None:
        from voicevision.backends.audio_duplex import DuplexConfig
        from voicevision.listen import ListenSession

        vad, stt = self._fakes()
        streams: list[FakeDuplexStream] = []
        session = ListenSession(
            vad=vad,  # type: ignore[arg-type]
            stt=stt,
            duplex_config=DuplexConfig(),
            duplex_stream_factory=self._factory(streams),  # type: ignore[arg-type]
        )
        session.start()
        try:
            session.play(b"\x01\x02" * 100)
            with session._duplex_session._lock:  # type: ignore[union-attr]
                assert len(session._duplex_session._playback) == 200  # type: ignore[union-attr]
        finally:
            session.stop()

    def test_barge_in_callback_invoked(self) -> None:
        from voicevision.backends.audio_duplex import DuplexConfig
        from voicevision.listen import ListenSession

        vad, stt = self._fakes()
        streams: list[FakeDuplexStream] = []
        notified: list[str] = []
        session = ListenSession(
            vad=vad,  # type: ignore[arg-type]
            stt=stt,
            duplex_config=DuplexConfig(),
            duplex_stream_factory=self._factory(streams),  # type: ignore[arg-type]
            on_barge_in=lambda: notified.append("interrupted"),
        )
        session.start()
        try:
            detector = session._duplex_session.detector  # type: ignore[union-attr]
            detector.set_playback(True)  # type: ignore[union-attr]
            import numpy as np

            speech = bytes((np.full(160, 0.7 * 32768, dtype="<i2")).tobytes())
            detector.begin_frame()  # type: ignore[union-attr]
            assert detector.process(speech) is True  # type: ignore[union-attr]
            assert notified == ["interrupted"]
            assert session.barge_in_latency_ms is not None
        finally:
            session.stop()
